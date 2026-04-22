"""mitmproxy addon — records HTTP(S) traffic to SQLite, tagged by active session."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from mitmproxy import http

if TYPE_CHECKING:
    from scout.collector.control import ControlServer
    from scout.collector.db import RecordingDB


class RecordingAddon:
    """mitmproxy addon that records request/response pairs to SQLite."""

    def __init__(self, db: RecordingDB, control: ControlServer) -> None:
        self._db = db
        self._control = control
        self._pending: dict[str, float] = {}

    def request(self, flow: http.HTTPFlow) -> None:
        self._pending[flow.id] = time.monotonic()

    def response(self, flow: http.HTTPFlow) -> None:
        session_id = self._control.active_session_id
        if session_id is None:
            self._pending.pop(flow.id, None)
            return

        start = self._pending.pop(flow.id, None)
        duration_ms = int((time.monotonic() - start) * 1000) if start else None

        req = flow.request
        resp = flow.response

        self._db.insert_api_record(
            scenario_id=session_id,
            method=req.method,
            url=req.pretty_url,
            request_headers=json.dumps(dict(req.headers)),
            request_body=req.content,
            status_code=resp.status_code if resp else None,
            response_headers=json.dumps(dict(resp.headers)) if resp else None,
            response_body=resp.content if resp else None,
            duration_ms=duration_ms,
        )
