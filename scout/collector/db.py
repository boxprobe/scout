"""Recording SQLite — scenario sessions and API records."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    scenario    TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    stopped_at  TEXT,
    UNIQUE(run_id, scenario)
);

CREATE TABLE IF NOT EXISTS api_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id      INTEGER NOT NULL REFERENCES scenarios(id),
    timestamp        TEXT NOT NULL,
    method           TEXT NOT NULL,
    url              TEXT NOT NULL,
    request_headers  TEXT,
    request_body     BLOB,
    status_code      INTEGER,
    response_headers TEXT,
    response_body    BLOB,
    duration_ms      INTEGER
);
"""


class RecordingDB:
    """SQLite-backed storage for proxy recording data."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def start_session(self, run_id: str, scenario: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO scenarios (run_id, scenario, started_at) VALUES (?, ?, ?)",
            (run_id, scenario, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def stop_session(self, scenario_id: int) -> None:
        self._conn.execute(
            "UPDATE scenarios SET stopped_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), scenario_id),
        )
        self._conn.commit()

    def get_session(self, scenario_id: int) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
        return dict(row)

    def insert_api_record(
        self,
        *,
        scenario_id: int,
        method: str,
        url: str,
        status_code: int | None = None,
        request_headers: str | None = None,
        request_body: bytes | None = None,
        response_headers: str | None = None,
        response_body: bytes | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO api_records
               (scenario_id, timestamp, method, url, request_headers, request_body,
                status_code, response_headers, response_body, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scenario_id, datetime.now(UTC).isoformat(), method, url,
             request_headers, request_body, status_code, response_headers,
             response_body, duration_ms),
        )
        self._conn.commit()

    def get_api_records(self, scenario_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM api_records WHERE scenario_id = ? ORDER BY id",
            (scenario_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
