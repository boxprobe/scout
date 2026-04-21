"""Tests for scout CLI `runs` command and run metadata recording."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from scout.cli import main
from scout.index import IndexDB
from scout.run_metadata import RunMetadata


def _seed_index(data_dir: Path, runs: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    db = IndexDB(data_dir / "index.db")
    for r in runs:
        defaults = dict(
            timestamp="2026-04-21T10:00:00+00:00",
            scenario="login/email",
            app="medusa-admin",
            app_version="2.1.0",
            env="qa1",
            commit=None,
            branch=None,
            scout_version="0.1.0",
        )
        defaults.update(r)
        db.insert(RunMetadata(**defaults))
    db.close()


def test_runs_lists_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Seeding 2 runs and invoking `runs` shows both run_ids in output."""
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / ".scout"
    _seed_index(
        data_dir,
        [
            {"run_id": "run-aaa"},
            {"run_id": "run-bbb"},
        ],
    )

    runner = CliRunner()
    result = runner.invoke(main, ["runs"])

    assert result.exit_code == 0, result.output
    assert "run-aaa" in result.output
    assert "run-bbb" in result.output


def test_runs_filter_by_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Filtering by --app returns only runs for that app."""
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / ".scout"
    _seed_index(
        data_dir,
        [
            {"run_id": "run-alpha", "app": "app-alpha"},
            {"run_id": "run-beta", "app": "app-beta"},
        ],
    )

    runner = CliRunner()
    result = runner.invoke(main, ["runs", "--app", "app-alpha"])

    assert result.exit_code == 0, result.output
    assert "run-alpha" in result.output
    assert "run-beta" not in result.output


def test_runs_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no index.db exists, output contains 'No runs found.'"""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["runs"])

    assert result.exit_code == 0, result.output
    assert "No runs found." in result.output
