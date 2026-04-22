"""Tests for scout.runner.executor — Playwright lifecycle + scenario execution."""

from unittest.mock import AsyncMock, patch

import pytest

from scout.runner.executor import execute_scenario
from scout.runner.scenario import Scenario


@pytest.fixture
def scenario():
    s = Scenario(name="test-scenario", base_url="http://localhost:3000", viewport_width=1280)

    @s.test
    async def test_fn(page):
        await page.goto("/")

    return s


def _mock_playwright():
    """Create mock Playwright objects (pw_instance → browser → context → page)."""
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = AsyncMock()
    mock_pw.chromium.launch.return_value = mock_browser

    mock_start = AsyncMock(return_value=mock_pw)
    return mock_start, mock_pw, mock_browser, mock_page


async def test_execute_scenario_success(scenario):
    """Successful scenario returns success=True."""
    mock_start, mock_pw, mock_browser, mock_page = _mock_playwright()

    with patch("scout.runner.executor.async_playwright") as mock_apw:
        mock_apw.return_value.start = mock_start
        result = await execute_scenario(scenario, headless=True)

    assert result.success is True
    assert result.errors == []
    assert result.duration_ms >= 0
    mock_browser.close.assert_called_once()
    mock_pw.stop.assert_called_once()


async def test_execute_scenario_failure(scenario):
    """Failed scenario returns success=False with error message."""
    mock_start, mock_pw, mock_browser, mock_page = _mock_playwright()
    mock_page.goto.side_effect = Exception("Navigation failed")

    @scenario.test
    async def failing_test(page):
        await page.pw.goto("/")

    with patch("scout.runner.executor.async_playwright") as mock_apw:
        mock_apw.return_value.start = mock_start
        result = await execute_scenario(scenario, headless=True)

    assert result.success is False
    assert len(result.errors) > 0
    assert "Navigation failed" in result.errors[0]
    mock_browser.close.assert_called_once()
    mock_pw.stop.assert_called_once()
