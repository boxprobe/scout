"""Run recording proxy in a child process."""

from __future__ import annotations

import asyncio
import multiprocessing
import time
from ctypes import c_int
from multiprocessing.sharedctypes import Synchronized

import httpx


def _run_proxy(
    proxy_port: int,
    control_port: int,
    shared_proxy_port: Synchronized,
    shared_control_port: Synchronized,
) -> None:
    """Entry point for the proxy child process."""

    async def _main() -> None:
        from scout.collector.control import ControlServer
        from scout.collector.proxy import RecordingAddon

        control = ControlServer(port=control_port)
        await control.start()
        shared_control_port.value = control.port

        from mitmproxy.options import Options
        from mitmproxy.tools.dump import DumpMaster

        opts = Options(listen_host="0.0.0.0", listen_port=proxy_port)  # noqa: S104  intentional: proxy must accept connections from spawned browsers
        master = DumpMaster(opts)
        master.addons.add(RecordingAddon(control))
        master.addons.add(_PortReporter(shared_proxy_port))

        try:
            await master.run()
        finally:
            await control.stop()

    asyncio.run(_main())


class _PortReporter:
    """Mitmproxy addon that writes resolved listen port to shared memory."""

    def __init__(self, shared_port: Synchronized) -> None:
        self._shared_port = shared_port

    def running(self) -> None:
        from mitmproxy import ctx

        ps = ctx.master.addons.get("proxyserver")
        if ps:
            addrs = ps.listen_addrs()
            if addrs:
                self._shared_port.value = addrs[0][1]


class ProxyProcess:
    """Manages a recording proxy in a child process with OS-assigned ports."""

    def __init__(self, proxy_port: int = 0, control_port: int = 0) -> None:
        self._requested_proxy_port = proxy_port
        self._requested_control_port = control_port
        self._shared_proxy_port = multiprocessing.Value(c_int, 0)
        self._shared_control_port = multiprocessing.Value(c_int, 0)
        self._process: multiprocessing.Process | None = None

    @property
    def proxy_addr(self) -> str:
        port = self._shared_proxy_port.value or self._requested_proxy_port
        return f"127.0.0.1:{port}"

    @property
    def control_base(self) -> str:
        port = self._shared_control_port.value or self._requested_control_port
        return f"http://127.0.0.1:{port}"

    def start(self, timeout: float = 10.0) -> None:
        """Start proxy in child process and wait until ready."""
        self._process = multiprocessing.Process(
            target=_run_proxy,
            args=(
                self._requested_proxy_port,
                self._requested_control_port,
                self._shared_proxy_port,
                self._shared_control_port,
            ),
            daemon=True,
        )
        self._process.start()

        # Wait for both control API and proxy to be ready
        deadline = time.monotonic() + timeout
        control_ready = False
        while time.monotonic() < deadline:
            control_port = self._shared_control_port.value
            proxy_port = self._shared_proxy_port.value
            if control_port and not control_ready:
                try:
                    resp = httpx.get(f"http://127.0.0.1:{control_port}/session/status", timeout=1)
                    if resp.status_code == 200:
                        control_ready = True
                except Exception:  # noqa: S110  control endpoint not ready yet — keep polling until deadline
                    pass
            if control_ready and proxy_port:
                return
            time.sleep(0.2)

        self.stop()
        raise RuntimeError("Recording proxy failed to start")

    def stop(self) -> None:
        """Stop the proxy child process."""
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.kill()
        self._process = None
