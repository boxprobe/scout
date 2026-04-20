"""Tests for scout.runner.page — Playwright page wrapper with Locator support."""

from unittest.mock import AsyncMock

import pytest

from scout.runner.locator import Locator
from scout.runner.page import Page


@pytest.fixture
def mock_pw_page():
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.mouse = AsyncMock()
    page.keyboard = AsyncMock()
    return page


@pytest.fixture
def page(mock_pw_page):
    return Page(mock_pw_page, base_url="https://example.com", wait_ms=1000)


async def test_goto_relative(page, mock_pw_page):
    """Relative URL prepends base_url."""
    await page.goto("/login")
    mock_pw_page.goto.assert_called_once_with("https://example.com/login")


async def test_goto_absolute(page, mock_pw_page):
    """Absolute URL used as-is."""
    await page.goto("https://other.com/page")
    mock_pw_page.goto.assert_called_once_with("https://other.com/page")


async def test_click(page, mock_pw_page):
    """Click resolves locator center and clicks."""
    loc = Locator(name="btn", tag="button", bbox=(100, 200, 60, 40))
    await page.click(loc)
    mock_pw_page.mouse.click.assert_called_once_with(130, 220)


async def test_fill(page, mock_pw_page):
    """Fill clicks the locator then types the value."""
    loc = Locator(name="email", tag="input", bbox=(50, 100, 200, 30))
    await page.fill(loc, "test@example.com")
    mock_pw_page.mouse.click.assert_called_once_with(150, 115)
    mock_pw_page.keyboard.press.assert_any_call("Control+a")
    mock_pw_page.keyboard.type.assert_called_once_with("test@example.com")


async def test_hover(page, mock_pw_page):
    """Hover moves mouse to locator center."""
    loc = Locator(name="menu", tag="div", bbox=(10, 20, 100, 50))
    await page.hover(loc)
    mock_pw_page.mouse.move.assert_called_once_with(60, 45)
