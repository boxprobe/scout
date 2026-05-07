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
    web_version   TEXT,
    api_version   TEXT,
    scenario      TEXT,
    env           TEXT,
    web_commit    TEXT,
    api_commit    TEXT,
    scenario_commit TEXT,
    scout_version TEXT,
    uploaded      INTEGER DEFAULT 0,
    local_path    TEXT,
    UNIQUE(run_id, scenario)
);
"""

# Migration: rename app_version → web_version + api_version for existing DBs
_MIGRATIONS = [
    "ALTER TABLE runs ADD COLUMN web_version TEXT;",
    "ALTER TABLE runs ADD COLUMN api_version TEXT;",
    "ALTER TABLE runs ADD COLUMN web_commit TEXT;",
    "ALTER TABLE runs ADD COLUMN api_commit TEXT;",
    "ALTER TABLE runs ADD COLUMN scenario_commit TEXT;",
]

_INSERT = """
INSERT OR IGNORE INTO runs
    (run_id, timestamp, app, web_version, api_version, scenario, env,
     web_commit, api_commit, scenario_commit, scout_version, uploaded, local_path)
VALUES
    (:run_id, :timestamp, :app, :web_version, :api_version, :scenario, :env,
     :web_commit, :api_commit, :scenario_commit, :scout_version, 0, :local_path);
"""

_FILTERABLE = {
    "app": "app",
    "scenario": "scenario",
    "web_version": "web_version",
    "api_version": "api_version",
    "env": "env",
}


class IndexDB:
    """SQLite-backed index of run metadata."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CREATE_TABLE)
        self._migrate()

    def _migrate(self) -> None:
        """Add missing columns for schema upgrades on existing DBs."""
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(runs)")}
        for stmt in _MIGRATIONS:
            # Extract column name from "ALTER TABLE runs ADD COLUMN <name> TEXT;"
            col = stmt.split("ADD COLUMN ")[1].split()[0]
            if col not in cols:
                try:
                    self._conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass

    def insert(self, meta: RunMetadata, local_path: str | None = None) -> None:
        """Insert a run row; silently skips duplicates (idempotent by run_id+scenario)."""
        self._conn.execute(
            _INSERT,
            {
                "run_id": meta.run_id,
                "timestamp": meta.timestamp,
                "app": meta.app,
                "web_version": meta.web_version,
                "api_version": meta.api_version,
                "scenario": meta.scenario,
                "env": meta.env,
                "web_commit": meta.web_commit,
                "api_commit": meta.api_commit,
                "scenario_commit": meta.scenario_commit,
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
        web_version: str | None = None,
        api_version: str | None = None,
        env: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return runs matching all supplied filters, newest first."""
        filters: dict[str, str] = {}
        if app is not None:
            filters["app"] = app
        if scenario is not None:
            filters["scenario"] = scenario
        if web_version is not None:
            filters["web_version"] = web_version
        if api_version is not None:
            filters["api_version"] = api_version
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
