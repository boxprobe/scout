"""Diff result SQLite — stores endpoint comparison results."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS endpoint_diffs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_record_id INTEGER,
    target_record_id   INTEGER,
    method             TEXT NOT NULL,
    path               TEXT NOT NULL,
    status_match       INTEGER NOT NULL,
    baseline_status    INTEGER,
    target_status      INTEGER,
    structure_match    INTEGER NOT NULL,
    diff_summary       TEXT,
    value_match        INTEGER,
    value_diff         TEXT,
    baseline_url       TEXT,
    baseline_request   TEXT,
    baseline_response  TEXT,
    baseline_timestamp TEXT,
    baseline_duration  INTEGER,
    target_url         TEXT,
    target_request     TEXT,
    target_response    TEXT,
    target_timestamp   TEXT,
    target_duration    INTEGER
);

CREATE TABLE IF NOT EXISTS missing_endpoints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    side        TEXT NOT NULL,
    record_id   INTEGER NOT NULL,
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    status_code INTEGER
);
"""


class DiffDB:
    """SQLite-backed storage for diff results."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def set_meta(
        self,
        baseline_run_id: str,
        target_run_id: str,
        app: str,
        scenario: str,
    ) -> None:
        for key, value in [
            ("baseline_run_id", baseline_run_id),
            ("target_run_id", target_run_id),
            ("app", app),
            ("scenario", scenario),
        ]:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (key, value),
            )
        self._conn.commit()

    def get_meta(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def insert_endpoint_diff(
        self,
        *,
        baseline_record_id: int | None,
        target_record_id: int | None,
        method: str,
        path: str,
        status_match: bool,
        baseline_status: int | None,
        target_status: int | None,
        structure_match: bool,
        diff_summary: str,
        value_match: bool = True,
        value_diff: str = "",
        baseline_url: str | None = None,
        baseline_request: str | None = None,
        baseline_response: str | None = None,
        baseline_timestamp: str | None = None,
        baseline_duration: int | None = None,
        target_url: str | None = None,
        target_request: str | None = None,
        target_response: str | None = None,
        target_timestamp: str | None = None,
        target_duration: int | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO endpoint_diffs
               (baseline_record_id, target_record_id, method, path,
                status_match, baseline_status, target_status,
                structure_match, diff_summary, value_match, value_diff,
                baseline_url, baseline_request, baseline_response,
                baseline_timestamp, baseline_duration,
                target_url, target_request, target_response,
                target_timestamp, target_duration)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (baseline_record_id, target_record_id, method, path,
             int(status_match), baseline_status, target_status,
             int(structure_match), diff_summary,
             int(value_match), value_diff,
             baseline_url, baseline_request, baseline_response,
             baseline_timestamp, baseline_duration,
             target_url, target_request, target_response,
             target_timestamp, target_duration),
        )
        self._conn.commit()

    def insert_missing_endpoint(
        self,
        *,
        side: str,
        record_id: int,
        method: str,
        path: str,
        status_code: int | None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO missing_endpoints
               (side, record_id, method, path, status_code)
               VALUES (?, ?, ?, ?, ?)""",
            (side, record_id, method, path, status_code),
        )
        self._conn.commit()

    def get_endpoint_diffs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM endpoint_diffs ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_missing_endpoints(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM missing_endpoints ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict[str, int]:
        paired = self._conn.execute("SELECT COUNT(*) FROM endpoint_diffs").fetchone()[0]
        status_mm = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE status_match = 0"
        ).fetchone()[0]
        struct_mm = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE structure_match = 0"
        ).fetchone()[0]
        value_mm = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE value_match = 0"
        ).fetchone()[0]
        missing = self._conn.execute("SELECT COUNT(*) FROM missing_endpoints").fetchone()[0]
        return {
            "total_paired": paired,
            "status_mismatches": status_mm,
            "structure_mismatches": struct_mm,
            "value_mismatches": value_mm,
            "missing_endpoints": missing,
        }

    def close(self) -> None:
        self._conn.close()
