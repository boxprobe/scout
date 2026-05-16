"""Tests for scout CLI commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from scout.cli import main


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a minimal delivery repo with app.json and one scenario."""
    (tmp_path / "app.json").write_text(
        json.dumps(
            {
                "name": "test-app",
                "web_base_url": "http://localhost",
            }
        )
    )
    sc = tmp_path / "scenarios" / "demo" / "hello"
    sc.mkdir(parents=True)
    (sc / "test.py").write_text(
        "from scout.runner import Scenario, Page\n"
        'scenario = Scenario(name="hello", base_url="http://localhost")\n'
        "@scenario.test\n"
        "async def test(page: Page):\n"
        "    pass\n"
    )
    return tmp_path


def test_cli_help() -> None:
    """CLI --help exits 0 and shows commands."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "verify" in result.output
    assert "record" in result.output


def test_cli_run_missing_path() -> None:
    """run with no paths shows error."""
    runner = CliRunner()
    result = runner.invoke(main, ["run"])
    assert result.exit_code != 0


def test_cli_verify_missing_path() -> None:
    """verify with no paths shows error."""
    runner = CliRunner()
    result = runner.invoke(main, ["verify"])
    assert result.exit_code != 0


def test_cli_diff_missing_args() -> None:
    """diff with no args shows error."""
    runner = CliRunner()
    result = runner.invoke(main, ["diff"])
    assert result.exit_code != 0


def test_cli_diff_in_help() -> None:
    """diff command appears in --help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert "diff" in result.output
