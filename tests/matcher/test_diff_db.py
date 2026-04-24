"""Tests for matcher/diff_db.py — diff result SQLite storage."""

from pathlib import Path

import pytest

from scout.matcher.diff_db import DiffDB


@pytest.fixture
def db(tmp_path: Path) -> DiffDB:
    ddb = DiffDB(tmp_path / "diff.db")
    yield ddb
    ddb.close()


def test_insert_and_get_endpoint_diff(db: DiffDB) -> None:
    db.insert_endpoint_diff(
        baseline_record_id=1,
        target_record_id=2,
        method="GET",
        path="/admin/orders",
        status_match=True,
        baseline_status=200,
        target_status=200,
        structure_match=True,
        diff_summary="",
    )
    rows = db.get_endpoint_diffs()
    assert len(rows) == 1
    assert rows[0]["method"] == "GET"
    assert rows[0]["status_match"] == 1


def test_insert_missing_endpoint(db: DiffDB) -> None:
    db.insert_missing_endpoint(
        side="target",
        record_id=5,
        method="GET",
        path="/admin/users",
        status_code=200,
    )
    rows = db.get_missing_endpoints()
    assert len(rows) == 1
    assert rows[0]["side"] == "target"


def test_set_and_get_meta(db: DiffDB) -> None:
    db.set_meta(
        baseline_run_id="20260423-a",
        target_run_id="20260423-b",
        app="medusa-admin",
    )
    meta = db.get_meta()
    assert meta["baseline_run_id"] == "20260423-a"
    assert meta["app"] == "medusa-admin"


def test_summary(db: DiffDB) -> None:
    db.insert_endpoint_diff(
        baseline_record_id=1, target_record_id=2,
        method="GET", path="/a",
        status_match=True, baseline_status=200, target_status=200,
        structure_match=True, diff_summary="",
        value_match=False, value_diff="≠ $.count: 5 → 10",
    )
    db.insert_endpoint_diff(
        baseline_record_id=3, target_record_id=4,
        method="GET", path="/b",
        status_match=False, baseline_status=200, target_status=500,
        structure_match=False, diff_summary="key removed",
    )
    db.insert_missing_endpoint(side="target", record_id=5, method="POST", path="/c", status_code=201)
    s = db.summary()
    assert s["total_paired"] == 2
    assert s["status_mismatches"] == 1
    assert s["structure_mismatches"] == 1
    assert s["value_mismatches"] == 1
    assert s["missing_endpoints"] == 1
