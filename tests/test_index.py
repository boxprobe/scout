"""Tests for scout.index — local SQLite index for run metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from scout.index import IndexDB
from scout.run_metadata import RunMetadata


def _make_meta(**overrides) -> RunMetadata:
    """Create a RunMetadata with sensible defaults, allowing field overrides."""
    defaults = {
        "run_id": "run-default-id",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "scenario": "tests/login.py",
        "app": "medusa-admin",
        "web_version": "2.3.1",
        "api_version": "2.3.1",
        "env": "staging",
        "web_commit": "abc123",
        "api_commit": "abc123",
        "scenario_commit": "def789",
        "scout_version": "0.1.0",
    }
    defaults.update(overrides)
    return RunMetadata(**defaults)


@pytest.fixture
def db(tmp_path: Path) -> IndexDB:
    """Provide a fresh IndexDB backed by a temp file."""
    index = IndexDB(tmp_path / "index.db")
    yield index
    index.close()


def test_insert_and_query(db: IndexDB) -> None:
    """Insert one run, query with no filters, verify run_id is present."""
    meta = _make_meta(run_id="run-001")
    db.insert(meta)

    rows = db.query()

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-001"


def test_query_by_app(db: IndexDB) -> None:
    """Two different apps — filtering by one returns only its runs."""
    db.insert(_make_meta(run_id="run-a1", app="app-alpha"))
    db.insert(_make_meta(run_id="run-b1", app="app-beta"))

    rows = db.query(app="app-alpha")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-a1"


def test_query_by_scenario(db: IndexDB) -> None:
    """Two different scenarios — filtering by one returns only its runs."""
    db.insert(_make_meta(run_id="run-s1", scenario="tests/login.py"))
    db.insert(_make_meta(run_id="run-s2", scenario="tests/checkout.py"))

    rows = db.query(scenario="tests/login.py")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-s1"


def test_query_by_web_version(db: IndexDB) -> None:
    """Filter by web_version returns only matching runs."""
    db.insert(_make_meta(run_id="run-v1", web_version="2.3.0"))
    db.insert(_make_meta(run_id="run-v2", web_version="2.4.0"))

    rows = db.query(web_version="2.3.0")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-v1"


def test_query_combined_filters(db: IndexDB) -> None:
    """Combining app + scenario filters returns only the intersection."""
    db.insert(_make_meta(run_id="run-c1", app="app-alpha", scenario="tests/login.py"))
    db.insert(_make_meta(run_id="run-c2", app="app-alpha", scenario="tests/checkout.py"))
    db.insert(_make_meta(run_id="run-c3", app="app-beta", scenario="tests/login.py"))

    rows = db.query(app="app-alpha", scenario="tests/login.py")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-c1"


def test_idempotent_insert(db: IndexDB) -> None:
    """Inserting the same run_id+scenario twice does not raise and results in one row."""
    meta = _make_meta(run_id="run-dup")
    db.insert(meta)
    db.insert(meta)  # should not raise

    rows = db.query()

    assert len(rows) == 1


def test_multiple_scenarios_per_run(db: IndexDB) -> None:
    """A single run_id can have multiple scenario rows."""
    db.insert(_make_meta(run_id="run-batch", scenario="auth/login"))
    db.insert(_make_meta(run_id="run-batch", scenario="auth/logout"))
    db.insert(_make_meta(run_id="run-batch", scenario="checkout/cart"))

    rows = db.query()

    assert len(rows) == 3
    assert all(r["run_id"] == "run-batch" for r in rows)


def test_empty_db_query(db: IndexDB) -> None:
    """Querying an empty database returns an empty list."""
    rows = db.query()

    assert rows == []


def test_query_ordered_by_timestamp_desc(db: IndexDB) -> None:
    """Rows are returned newest-first (ORDER BY timestamp DESC)."""
    db.insert(_make_meta(run_id="run-old", timestamp="2026-01-01T00:00:00+00:00"))
    db.insert(_make_meta(run_id="run-new", timestamp="2026-06-01T00:00:00+00:00"))

    rows = db.query()

    assert rows[0]["run_id"] == "run-new"
    assert rows[1]["run_id"] == "run-old"
