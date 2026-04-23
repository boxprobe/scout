"""Tests for collector/db.py — recording SQLite schema and operations."""

from pathlib import Path

import pytest

from scout.collector.db import RecordingDB


@pytest.fixture
def db(tmp_path: Path) -> RecordingDB:
    rdb = RecordingDB(tmp_path / "record.db")
    yield rdb
    rdb.close()


def test_start_and_stop_session(db: RecordingDB) -> None:
    sid = db.start_session("run-001", "auth/login-success")
    assert sid > 0
    db.stop_session(sid)
    row = db.get_session(sid)
    assert row["run_id"] == "run-001"
    assert row["scenario"] == "auth/login-success"
    assert row["started_at"] is not None
    assert row["stopped_at"] is not None


def test_insert_api_record(db: RecordingDB) -> None:
    sid = db.start_session("run-001", "auth/login")
    db.insert_api_record(
        scenario_id=sid, method="POST", url="http://localhost:9000/admin/auth",
        request_headers='{"Content-Type":"application/json"}',
        request_body='{"email":"test@test.com"}',
        status_code=200,
        response_headers='{"Content-Type":"application/json"}',
        response_body='{"token":"abc"}',
        duration_ms=45,
    )
    records = db.get_api_records(sid)
    assert len(records) == 1
    assert records[0]["method"] == "POST"
    assert records[0]["status_code"] == 200
    assert records[0]["duration_ms"] == 45


def test_no_records_outside_session(db: RecordingDB) -> None:
    sid = db.start_session("run-001", "auth/login")
    records = db.get_api_records(sid)
    assert records == []


def test_multiple_sessions(db: RecordingDB) -> None:
    sid1 = db.start_session("run-001", "scenario-a")
    db.insert_api_record(scenario_id=sid1, method="GET", url="http://a", status_code=200)
    db.stop_session(sid1)
    sid2 = db.start_session("run-001", "scenario-b")
    db.insert_api_record(scenario_id=sid2, method="POST", url="http://b", status_code=201)
    db.stop_session(sid2)
    assert len(db.get_api_records(sid1)) == 1
    assert len(db.get_api_records(sid2)) == 1
    assert db.get_api_records(sid1)[0]["url"] == "http://a"
    assert db.get_api_records(sid2)[0]["url"] == "http://b"
