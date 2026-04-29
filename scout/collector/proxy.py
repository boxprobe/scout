"""mitmproxy addon — records HTTP(S) traffic to SQLite, tagged by active session."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from mitmproxy import http

if TYPE_CHECKING:
    from scout.collector.control import ControlServer


_SESSION_HEADER = "X-Scout-Session"


class RecordingAddon:
    """mitmproxy addon that records request/response pairs to SQLite."""

    def __init__(self, control: ControlServer) -> None:
        self._control = control
        self._pending: dict[str, tuple[float, str | None]] = {}  # flow_id → (start_time, scenario)

    def request(self, flow: http.HTTPFlow) -> None:
        # Extract and strip session header before forwarding
        scenario = flow.request.headers.pop(_SESSION_HEADER, None)
        self._pending[flow.id] = (time.monotonic(), scenario)

    def response(self, flow: http.HTTPFlow) -> None:
        entry = self._pending.pop(flow.id, None)
        if entry is None:
            return
        start_time, scenario = entry

        session_id = self._control.session_id_for(scenario) if scenario else None
        if session_id is None:
            return

        db = self._control.db
        if db is None:
            self._pending.pop(flow.id, None)
            return

        # Only record requests matching api_base_url
        api_base = self._control.api_base_url
        if api_base and not flow.request.pretty_url.startswith(api_base):
            self._pending.pop(flow.id, None)
            return

        duration_ms = int((time.monotonic() - start_time) * 1000)

        req = flow.request
        resp = flow.response

        db.insert_api_record(
            scenario_id=session_id,
            method=req.method,
            url=req.pretty_url,
            request_headers=json.dumps(dict(req.headers)),
            request_body=req.text if req.content else None,
            status_code=resp.status_code if resp else None,
            response_headers=json.dumps(dict(resp.headers)) if resp else None,
            response_body=resp.text if resp and resp.content else None,
            duration_ms=duration_ms,
        )
