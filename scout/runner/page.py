"""Page — Locator-aware wrapper over a Playwright page.

Translates high-level actions (click, fill, goto) into Playwright calls
using Locator coordinates for element positioning.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page as PwPage

from scout.runner.locator import Locator


class Page:
    """Thin wrapper that resolves Locators to Playwright mouse/keyboard actions."""

    def __init__(self, pw_page: PwPage, *, base_url: str = "", wait_ms: int = 0) -> None:
        self._page = pw_page
        self._base_url = base_url.rstrip("/")
        self._wait_ms = wait_ms

    async def goto(self, url: str) -> None:
        """Navigate to a URL. Relative paths are prepended with base_url."""
        if url.startswith("/"):
            url = f"{self._base_url}{url}"
        await self._page.goto(url)

    async def click(self, locator: Locator) -> None:
        """Click the center of a locator."""
        x, y = locator.center()
        await self._page.mouse.click(x, y)

    async def fill(self, locator: Locator, value: str) -> None:
        """Click a locator to focus, select all, then type the value."""
        x, y = locator.center()
        await self._page.mouse.click(x, y)
        await self._page.keyboard.press("Control+a")
        await self._page.keyboard.type(value)

    async def hover(self, locator: Locator) -> None:
        """Hover over the center of a locator."""
        x, y = locator.center()
        await self._page.mouse.move(x, y)

    async def wait(self, ms: int | None = None) -> None:
        """Wait for a given number of milliseconds (default: scenario wait_ms)."""
        delay = ms if ms is not None else self._wait_ms
        if delay > 0:
            await asyncio.sleep(delay / 1000)

    @property
    def pw(self) -> PwPage:
        """Access the underlying Playwright page for advanced usage."""
        return self._page
