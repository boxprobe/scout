"""Control API — lightweight HTTP server for proxy session management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from scout.collector.db import RecordingDB


class ControlServer:
    """HTTP server exposing /session/start, /session/stop, /session/status."""

    def __init__(self, db: RecordingDB | None = None, port: int = 8081) -> None:
        self._db = db
        self._requested_port = port
        # Concurrent session support: scenario_path → session_id
        self._sessions: dict[str, int] = {}
        self._api_base_url: str | None = None
        self._app = web.Application()
        self._app.router.add_post("/session/start", self._handle_start)
        self._app.router.add_post("/session/stop", self._handle_stop)
        self._app.router.add_get("/session/status", self._handle_status)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.port: int = port

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", self._requested_port)
        await self._site.start()
        # Resolve actual port (important when port=0)
        sock = self._site._server.sockets[0]
        self.port = sock.getsockname()[1]

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    def session_id_for(self, scenario: str) -> int | None:
        """Look up session_id by scenario path (used by proxy addon)."""
        return self._sessions.get(scenario)

    @property
    def api_base_url(self) -> str | None:
        return self._api_base_url

    @property
    def db(self) -> RecordingDB | None:
        return self._db

    async def _handle_start(self, request: web.Request) -> web.Response:
        body = await request.json()
        scenario = body["scenario"]
        run_id = body["run_id"]

        # Per-run DB: caller can specify where to write
        db_path = body.get("db_path")
        if db_path:
            from scout.collector.db import RecordingDB
            # Close previous DB if it was created per-run
            if self._db is not None:
                self._db.close()
            self._db = RecordingDB(Path(db_path))

        if self._db is None:
            return web.json_response({"error": "no db configured"}, status=400)

        # URL filter: only record requests matching this prefix
        self._api_base_url = body.get("api_base_url")

        sid = self._db.start_session(
            run_id,
            scenario,
            app=body.get("app"),
            web_version=body.get("web_version"),
            api_version=body.get("api_version"),
            env=body.get("env"),
            web_commit=body.get("web_commit"),
            api_commit=body.get("api_commit"),
            scenario_commit=body.get("scenario_commit"),
            scout_version=body.get("scout_version"),
        )
        self._sessions[scenario] = sid
        return web.json_response({"scenario_id": sid})

    async def _handle_stop(self, request: web.Request) -> web.Response:
        body = await request.json()
        scenario = body.get("scenario")
        sid = self._sessions.pop(scenario, None) if scenario else None
        if sid is not None and self._db is not None:
            self._db.stop_session(sid)
        return web.json_response({"ok": True})

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "active": len(self._sessions) > 0,
            "sessions": self._sessions,
        })
