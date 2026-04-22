"""Tests for collector/control.py — session control API."""

from pathlib import Path

import httpx
import pytest

from scout.collector.control import ControlServer
from scout.collector.db import RecordingDB


@pytest.fixture
def db(tmp_path: Path) -> RecordingDB:
    rdb = RecordingDB(tmp_path / "record.db")
    yield rdb
    rdb.close()


@pytest.fixture
async def server(db: RecordingDB):
    srv = ControlServer(db, port=0)
    await srv.start()
    yield srv
    await srv.stop()


async def test_session_start_stop(server: ControlServer, db: RecordingDB) -> None:
    base = f"http://127.0.0.1:{server.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base}/session/start",
            json={"scenario": "auth/login", "run_id": "run-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] > 0

        resp = await client.post(f"{base}/session/stop")
        assert resp.status_code == 200

        resp = await client.get(f"{base}/session/status")
        assert resp.status_code == 200
        assert resp.json()["active"] is False


async def test_session_status_when_active(server: ControlServer) -> None:
    base = f"http://127.0.0.1:{server.port}"
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base}/session/start",
            json={"scenario": "auth/login", "run_id": "run-001"},
        )
        resp = await client.get(f"{base}/session/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is True
        assert body["scenario"] == "auth/login"
