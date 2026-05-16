"""Tests for scout.runner.page — Playwright page wrapper with Locator support."""

from unittest.mock import AsyncMock

import pytest

from scout.runner.locator import Locator
from scout.runner.page import Page


@pytest.fixture
def mock_pw_page():
    """Create a mock Playwright page with evaluate support for resolve()."""
    page = AsyncMock()
    page.mouse = AsyncMock()
    page.keyboard = AsyncMock()
    # evaluate returns None by default (no dynamic resize / no filter match)
    page.evaluate = AsyncMock(return_value=None)
    return page


@pytest.fixture
def page(mock_pw_page):
    return Page(mock_pw_page, base_url="https://example.com", wait_ms=1000)


async def test_goto_relative(page, mock_pw_page):
    """Relative URL prepends base_url."""
    await page.goto("/login")
    mock_pw_page.goto.assert_called_once_with(
        "https://example.com/login", wait_until="networkidle"
    )


async def test_goto_absolute(page, mock_pw_page):
    """Absolute URL used as-is."""
    await page.goto("https://other.com/page")
    mock_pw_page.goto.assert_called_once_with("https://other.com/page", wait_until="networkidle")


async def test_click(page, mock_pw_page):
    """Click resolves locator and clicks at center."""
    loc = Locator(name="btn", tag="button", bbox=(100, 200, 60, 40))
    await page.click(loc)
    mock_pw_page.mouse.click.assert_called_once_with(130, 220, delay=100)


async def test_fill(page, mock_pw_page):
    """Fill resolves locator, clicks, selects all, then types."""
    loc = Locator(name="email", tag="input", bbox=(50, 100, 200, 30))
    await page.fill(loc, "test@example.com")
    mock_pw_page.mouse.click.assert_called_once_with(150, 115)
    mock_pw_page.keyboard.press.assert_any_call("Control+a")
    mock_pw_page.keyboard.type.assert_called_once_with("test@example.com")


async def test_hover(page, mock_pw_page):
    """Hover resolves locator and moves to center."""
    loc = Locator(name="menu", tag="div", bbox=(10, 20, 100, 50))
    await page.hover(loc)
    mock_pw_page.mouse.move.assert_called_once_with(60, 45)


async def test_click_with_registry(mock_pw_page):
    """Page with locator registry resolves rel locators correctly."""
    parent = Locator(name="form", tag="form", bbox=(100, 200, 400, 300))
    child = Locator(
        name="submit",
        tag="button",
        bbox=(0, 0, 80, 40),
        pos_type="dxy",
        parent="form",
        pos_offset={"dx": 10, "dy": 10},
    )
    registry = {"form": parent, "submit": child}
    page = Page(mock_pw_page, base_url="https://example.com", locator_registry=registry)
    await page.click(child)
    # resolved: x=110, y=210, w=80, h=40 → center (150, 230)
    mock_pw_page.mouse.click.assert_called_once_with(150, 230, delay=100)


async def test_select_option(page, mock_pw_page):
    """select_option resolves locator and evaluates JS to set <select> value."""
    loc = Locator(name="country", tag="select", bbox=(100, 200, 150, 30))
    await page.select_option(loc, "us")
    mock_pw_page.evaluate.assert_called()
    # Last evaluate call is the select_option JS (earlier calls are scroll + marker)
    args = mock_pw_page.evaluate.call_args
    assert args[0][1] == [pytest.approx(175, abs=1), pytest.approx(215, abs=1), "us"]
