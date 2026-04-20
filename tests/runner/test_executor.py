"""Tests for scout.runner.executor — Playwright lifecycle + scenario execution."""

from unittest.mock import AsyncMock, patch

import pytest

from scout.runner.executor import ExecutionResult, execute_scenario
from scout.runner.scenario import Scenario


@pytest.fixture
def scenario():
    s = Scenario(name="test-scenario", base_url="http://localhost:3000", viewport_width=1280)

    @s.test
    async def test_fn(page):
        await page.goto("/")

    return s


async def test_execute_scenario_success(scenario):
    """Successful scenario returns success=True."""
    with patch("scout.runner.executor._launch_browser") as mock_launch:
        mock_page = AsyncMock()
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_launch.return_value = (mock_pw, mock_browser, mock_page)

        result = await execute_scenario(scenario, headless=True)

        assert result.success is True
        assert result.errors == []
        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()


async def test_execute_scenario_failure(scenario):
    """Failed scenario returns success=False with error message."""
    with patch("scout.runner.executor._launch_browser") as mock_launch:
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Navigation failed")
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_launch.return_value = (mock_pw, mock_browser, mock_page)

        @scenario.test
        async def failing_test(page):
            await page.pw.goto("/")

        result = await execute_scenario(scenario, headless=True)

        assert result.success is False
        assert len(result.errors) > 0
        assert "Navigation failed" in result.errors[0]
        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()
