"""Local SQLite index — one row per run×scenario for metadata queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from scout.run_metadata import RunMetadata

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    app           TEXT,
    app_version   TEXT,
    scenario      TEXT,
    env           TEXT,
    commit_hash   TEXT,
    branch        TEXT,
    scout_version TEXT,
    uploaded      INTEGER DEFAULT 0,
    local_path    TEXT,
    UNIQUE(run_id, scenario)
);
"""

_INSERT = """
INSERT OR IGNORE INTO runs
    (run_id, timestamp, app, app_version, scenario, env,
     commit_hash, branch, scout_version, uploaded, local_path)
VALUES
    (:run_id, :timestamp, :app, :app_version, :scenario, :env,
     :commit_hash, :branch, :scout_version, 0, :local_path);
"""

_FILTERABLE = {
    "app": "app",
    "scenario": "scenario",
    "app_version": "app_version",
    "env": "env",
}


class IndexDB:
    """SQLite-backed index of run metadata."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CREATE_TABLE)

    def insert(self, meta: RunMetadata, local_path: str | None = None) -> None:
        """Insert a run row; silently skips duplicates (idempotent by run_id+scenario)."""
        self._conn.execute(
            _INSERT,
            {
                "run_id": meta.run_id,
                "timestamp": meta.timestamp,
                "app": meta.app,
                "app_version": meta.app_version,
                "scenario": meta.scenario,
                "env": meta.env,
                "commit_hash": meta.commit,
                "branch": meta.branch,
                "scout_version": meta.scout_version,
                "local_path": local_path,
            },
        )
        self._conn.commit()

    def query(
        self,
        *,
        app: str | None = None,
        scenario: str | None = None,
        app_version: str | None = None,
        env: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return runs matching all supplied filters, newest first."""
        filters: dict[str, str] = {}
        if app is not None:
            filters["app"] = app
        if scenario is not None:
            filters["scenario"] = scenario
        if app_version is not None:
            filters["app_version"] = app_version
        if env is not None:
            filters["env"] = env

        if filters:
            where = " AND ".join(f"{col} = :{col}" for col in filters)
            sql = f"SELECT * FROM runs WHERE {where} ORDER BY timestamp DESC"  # noqa: S608
        else:
            sql = "SELECT * FROM runs ORDER BY timestamp DESC"

        cursor = self._conn.execute(sql, filters)
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()
