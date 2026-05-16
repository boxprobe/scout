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
    scenario           TEXT,
    baseline_record_id INTEGER,
    target_record_id   INTEGER,
    method             TEXT NOT NULL,
    path               TEXT NOT NULL,
    step_seq           INTEGER,
    step_label         TEXT,
    baseline_offset_ms INTEGER,
    target_offset_ms   INTEGER,
    status_match       INTEGER NOT NULL,
    baseline_status    INTEGER,
    target_status      INTEGER,
    structure_match    INTEGER NOT NULL,
    diff_summary       TEXT,
    value_match        INTEGER,
    value_diff         TEXT,
    baseline_url               TEXT,
    baseline_request           TEXT,
    baseline_response          TEXT,
    baseline_request_headers   TEXT,
    baseline_response_headers  TEXT,
    baseline_timestamp         TEXT,
    baseline_duration          INTEGER,
    target_url                 TEXT,
    target_request             TEXT,
    target_response            TEXT,
    target_request_headers     TEXT,
    target_response_headers    TEXT,
    target_timestamp           TEXT,
    target_duration            INTEGER,
    header_match               INTEGER,
    header_diff                TEXT
);

CREATE TABLE IF NOT EXISTS missing_endpoints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario    TEXT,
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
        # Drop and recreate to ensure schema is up-to-date
        self._conn.executescript("""
            DROP TABLE IF EXISTS endpoint_diffs;
            DROP TABLE IF EXISTS missing_endpoints;
            DROP TABLE IF EXISTS meta;
        """)
        self._conn.executescript(_SCHEMA)

    def set_meta(
        self,
        baseline_run_id: str,
        target_run_id: str,
        app: str,
        baseline_version: str = "",
        target_version: str = "",
    ) -> None:
        for key, value in [
            ("baseline_run_id", baseline_run_id),
            ("target_run_id", target_run_id),
            ("app", app),
            ("baseline_version", baseline_version),
            ("target_version", target_version),
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
        scenario: str = "",
        baseline_record_id: int | None,
        target_record_id: int | None,
        method: str,
        path: str,
        step_seq: int | None = None,
        step_label: str | None = None,
        baseline_offset_ms: int | None = None,
        target_offset_ms: int | None = None,
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
        baseline_request_headers: str | None = None,
        baseline_response_headers: str | None = None,
        baseline_timestamp: str | None = None,
        baseline_duration: int | None = None,
        target_url: str | None = None,
        target_request: str | None = None,
        target_response: str | None = None,
        target_request_headers: str | None = None,
        target_response_headers: str | None = None,
        target_timestamp: str | None = None,
        target_duration: int | None = None,
        header_match: bool = True,
        header_diff: str = "",
    ) -> None:
        self._conn.execute(
            """INSERT INTO endpoint_diffs
               (scenario, baseline_record_id, target_record_id, method, path,
                step_seq, step_label, baseline_offset_ms, target_offset_ms,
                status_match, baseline_status, target_status,
                structure_match, diff_summary, value_match, value_diff,
                baseline_url, baseline_request, baseline_response,
                baseline_request_headers, baseline_response_headers,
                baseline_timestamp, baseline_duration,
                target_url, target_request, target_response,
                target_request_headers, target_response_headers,
                target_timestamp, target_duration,
                header_match, header_diff)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scenario,
                baseline_record_id,
                target_record_id,
                method,
                path,
                step_seq,
                step_label,
                baseline_offset_ms,
                target_offset_ms,
                int(status_match),
                baseline_status,
                target_status,
                int(structure_match),
                diff_summary,
                int(value_match),
                value_diff,
                baseline_url,
                baseline_request,
                baseline_response,
                baseline_request_headers,
                baseline_response_headers,
                baseline_timestamp,
                baseline_duration,
                target_url,
                target_request,
                target_response,
                target_request_headers,
                target_response_headers,
                target_timestamp,
                target_duration,
                int(header_match),
                header_diff,
            ),
        )
        self._conn.commit()

    def insert_missing_endpoint(
        self,
        *,
        scenario: str = "",
        side: str,
        record_id: int,
        method: str,
        path: str,
        status_code: int | None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO missing_endpoints
               (scenario, side, record_id, method, path, status_code)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (scenario, side, record_id, method, path, status_code),
        )
        self._conn.commit()

    def get_endpoint_diffs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM endpoint_diffs ORDER BY scenario, COALESCE(step_seq, 999999), COALESCE(baseline_offset_ms, 999999999), id"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_missing_endpoints(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM missing_endpoints ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict[str, int]:
        # Missing endpoints now live in endpoint_diffs with one side's record_id
        # NULL. Exclude these from status/structure/value mismatch counts so
        # they don't double-count: they're "endpoint changes", not body diffs.
        # SQL f-string OK: paired_where is a hardcoded local string, not user input.
        paired_where = "baseline_record_id IS NOT NULL AND target_record_id IS NOT NULL"
        paired = self._conn.execute(
            f"SELECT COUNT(*) FROM endpoint_diffs WHERE {paired_where}"  # noqa: S608
        ).fetchone()[0]
        status_mm = self._conn.execute(
            f"SELECT COUNT(*) FROM endpoint_diffs WHERE status_match = 0 AND {paired_where}"  # noqa: S608
        ).fetchone()[0]
        struct_mm = self._conn.execute(
            f"SELECT COUNT(*) FROM endpoint_diffs WHERE structure_match = 0 AND {paired_where}"  # noqa: S608
        ).fetchone()[0]
        value_mm = self._conn.execute(
            f"SELECT COUNT(*) FROM endpoint_diffs WHERE value_match = 0 AND {paired_where}"  # noqa: S608
        ).fetchone()[0]
        missing = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE baseline_record_id IS NULL OR target_record_id IS NULL"
        ).fetchone()[0]
        base_4xx = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE baseline_status >= 400 AND baseline_status < 500"
        ).fetchone()[0]
        base_5xx = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE baseline_status >= 500"
        ).fetchone()[0]
        target_4xx = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE target_status >= 400 AND target_status < 500"
        ).fetchone()[0]
        target_5xx = self._conn.execute(
            "SELECT COUNT(*) FROM endpoint_diffs WHERE target_status >= 500"
        ).fetchone()[0]
        return {
            "total_paired": paired,
            "status_mismatches": status_mm,
            "structure_mismatches": struct_mm,
            "value_mismatches": value_mm,
            "missing_endpoints": missing,
            "baseline_4xx": base_4xx,
            "baseline_5xx": base_5xx,
            "target_4xx": target_4xx,
            "target_5xx": target_5xx,
        }

    def close(self) -> None:
        self._conn.close()
