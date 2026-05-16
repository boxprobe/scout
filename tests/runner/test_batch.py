"""Tests for scout.runner.executor — batch execution + result output."""

import json
from unittest.mock import AsyncMock, patch

from scout.runner.executor import (
    ExecutionResult,
    _derive_scenario_path,
    _result_to_dict,
    execute_batch,
)


def _mock_playwright():
    """Create mock Playwright objects."""
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = AsyncMock()
    mock_pw.chromium.launch.return_value = mock_browser

    mock_start = AsyncMock(return_value=mock_pw)
    return mock_start, mock_pw, mock_browser, mock_page


def test_derive_scenario_path_from_scenarios_dir(tmp_path):
    """Derives path from scenarios/ parent directory."""
    test_file = tmp_path / "scenarios" / "auth" / "login-success" / "test.py"
    test_file.parent.mkdir(parents=True)
    test_file.touch()
    assert _derive_scenario_path(test_file) == "auth/login-success"


def test_derive_scenario_path_nested(tmp_path):
    """Derives nested scenario path."""
    test_file = tmp_path / "scenarios" / "checkout" / "payment" / "test.py"
    test_file.parent.mkdir(parents=True)
    test_file.touch()
    assert _derive_scenario_path(test_file) == "checkout/payment"


def test_derive_scenario_path_fallback(tmp_path):
    """Falls back to parent directory name when no 'scenarios' parent."""
    test_file = tmp_path / "some-dir" / "test.py"
    test_file.parent.mkdir(parents=True)
    test_file.touch()
    assert _derive_scenario_path(test_file) == "some-dir"


def test_result_to_dict():
    """ExecutionResult converts to JSON-serializable dict."""
    result = ExecutionResult(success=True, duration_ms=1234)
    d = _result_to_dict(result)
    assert d["success"] is True
    assert d["duration_ms"] == 1234
    assert d["errors"] == []
    assert "timestamp" in d


def test_result_to_dict_failure():
    """Failed result includes errors."""
    result = ExecutionResult(success=False, errors=["boom"], duration_ms=500)
    d = _result_to_dict(result)
    assert d["success"] is False
    assert d["errors"] == ["boom"]


async def test_execute_batch_writes_results(tmp_path):
    """Batch execution writes per-scenario JSON result files."""
    # Create two test.py files under scenarios/
    for name in ("auth/login", "auth/logout"):
        d = tmp_path / "scenarios" / name
        d.mkdir(parents=True)
        (d / "test.py").write_text(
            "from scout.runner import Scenario\n"
            f'scenario = Scenario(name="{name}", '
            'base_url="http://localhost", viewport_width=1280)\n'
            "@scenario.test\n"
            "async def test(page):\n"
            "    pass\n"
        )

    test_paths = [
        str(tmp_path / "scenarios/auth/login/test.py"),
        str(tmp_path / "scenarios/auth/logout/test.py"),
    ]
    results_dir = tmp_path / ".scout" / "results"

    mock_start, mock_pw, mock_browser, _mock_page = _mock_playwright()

    with patch("scout.runner.executor.async_playwright") as mock_apw:
        mock_apw.return_value.start = mock_start
        results = await execute_batch(test_paths, headless=True, results_dir=results_dir)

    # Both scenarios executed
    assert len(results) == 2
    assert results["auth/login"].success is True
    assert results["auth/logout"].success is True

    # Result files written
    login_result = results_dir / "auth" / "login" / "result.json"
    logout_result = results_dir / "auth" / "logout" / "result.json"
    assert login_result.exists()
    assert logout_result.exists()

    data = json.loads(login_result.read_text())
    assert data["success"] is True
    assert "timestamp" in data

    # Browser launched once, closed once
    mock_pw.chromium.launch.assert_called_once()
    mock_browser.close.assert_called_once()


async def test_execute_batch_file_not_found(tmp_path):
    """Missing test.py returns failure result without crashing batch."""
    results_dir = tmp_path / ".scout" / "results"
    results = await execute_batch(
        [str(tmp_path / "nonexistent/test.py")],
        headless=True,
        results_dir=results_dir,
    )

    # Should still have a result entry (failed)
    assert len(results) == 1
    result = next(iter(results.values()))
    assert result.success is False
    assert "not found" in result.errors[0].lower()
