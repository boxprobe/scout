"""Page — Locator-aware wrapper over a Playwright page.

Translates high-level actions (click, fill, goto) into Playwright calls.
Before each action, scrolls to the element's annotation-time scroll position,
resolves the Locator's coordinates, and optionally takes before/after screenshots.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page as PwPage

from scout.runner.locator import Locator


class Page:
    """Thin wrapper that resolves Locators to Playwright mouse/keyboard actions."""

    def __init__(
        self,
        pw_page: PwPage,
        *,
        base_url: str = "",
        wait_ms: int = 0,
        locator_registry: dict[str, Locator] | None = None,
        screenshot_dir: Path | None = None,
    ) -> None:
        self._page = pw_page
        self._base_url = base_url.rstrip("/")
        self._wait_ms = wait_ms
        self._registry: dict[str, Locator] = locator_registry or {}
        self._screenshot_dir = screenshot_dir
        self._step_counter = 0

    async def _scroll_and_resolve(self, locator: Locator) -> tuple[int, int]:
        """Scroll to locator's annotation-time position, then resolve coordinates."""
        # Auto-register locator so parent lookups work for rel/dxy
        self._registry[locator.name] = locator
        # Scroll to the position where the element was annotated
        await self._page.evaluate(f"window.scrollTo(0, {locator.scroll_y})")
        await locator.resolve(self._page, self._registry)
        return locator.center()

    async def _screenshot(self, sub: int) -> None:
        """Take a screenshot if screenshot_dir is configured.

        Filename format: {step}{sub}.png, e.g. 011.png (step 1, before),
        012.png (step 1, after). Natural sort order matches execution order.
        """
        if self._screenshot_dir is None:
            return
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self._screenshot_dir / f"{self._step_counter:02d}{sub}.png"
        await self._page.screenshot(path=path)

    async def _mark_target(self, x: int, y: int) -> None:
        """Draw a numbered circle marker at the click target for before-screenshots."""
        await self._page.evaluate(
            """([x, y, seq]) => {
                const marker = document.createElement('div');
                marker.id = '__scout-marker';
                Object.assign(marker.style, {
                    position: 'fixed', left: (x - 12) + 'px', top: (y - 12) + 'px',
                    width: '24px', height: '24px', borderRadius: '50%',
                    background: 'rgba(239, 68, 68, 0.85)',
                    border: '2px solid #fff',
                    boxShadow: '0 0 0 2px rgba(239, 68, 68, 0.5), 0 2px 8px rgba(0,0,0,0.3)',
                    zIndex: '2147483647', pointerEvents: 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff', fontSize: '11px', fontWeight: '700',
                    fontFamily: 'system-ui, sans-serif', lineHeight: '1',
                });
                marker.textContent = String(seq);
                document.body.appendChild(marker);
            }""",
            [x, y, self._step_counter],
        )

    async def _clear_marker(self) -> None:
        """Remove the click target marker."""
        await self._page.evaluate(
            "document.getElementById('__scout-marker')?.remove()"
        )

    async def goto(self, url: str) -> None:
        """Navigate to a URL. Relative paths are prepended with base_url."""
        self._step_counter += 1
        if url.startswith("/"):
            url = f"{self._base_url}{url}"
        await self._page.goto(url, wait_until="networkidle")
        await self._screenshot(1)

    async def click(self, locator: Locator) -> None:
        """Scroll, resolve locator coordinates, and click."""
        self._step_counter += 1
        x, y = await self._scroll_and_resolve(locator)
        await self._mark_target(x, y)
        await self._screenshot(1)
        await self._clear_marker()
        await self._page.mouse.move(x, y)
        await asyncio.sleep(0.15)
        await self._page.mouse.click(x, y, delay=100)
        await self._screenshot(2)

    async def fill(self, locator: Locator, value: str) -> None:
        """Scroll, resolve locator, click to focus, select all, then type the value."""
        self._step_counter += 1
        x, y = await self._scroll_and_resolve(locator)
        await self._mark_target(x, y)
        await self._screenshot(1)
        await self._clear_marker()
        await self._page.mouse.move(x, y)
        await asyncio.sleep(0.15)
        await self._page.mouse.click(x, y)
        await self._page.keyboard.press("Control+a")
        await self._page.keyboard.type(value)
        await self._screenshot(2)

    async def select_option(self, locator: Locator, value: str) -> None:
        """Scroll, resolve locator, and select an <option> by value."""
        self._step_counter += 1
        x, y = await self._scroll_and_resolve(locator)
        await self._mark_target(x, y)
        await self._screenshot(1)
        await self._clear_marker()
        # Use Playwright's native select_option via evaluate on the element at coordinates
        await self._page.evaluate(
            """([x, y, val]) => {
                const el = document.elementFromPoint(x, y);
                if (!el || el.tagName !== 'SELECT') throw new Error('No <select> at target');
                const nativeSetter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set;
                if (nativeSetter) nativeSetter.call(el, val);
                else el.value = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            [x, y, value],
        )
        await self._screenshot(2)

    async def hover(self, locator: Locator) -> None:
        """Scroll, resolve locator coordinates, and hover."""
        self._step_counter += 1
        x, y = await self._scroll_and_resolve(locator)
        await self._mark_target(x, y)
        await self._screenshot(1)
        await self._clear_marker()
        await self._page.mouse.move(x, y)
        await self._screenshot(2)

    async def wait(self, ms: int | None = None) -> None:
        """Wait for a given number of milliseconds (default: scenario wait_ms)."""
        delay = ms if ms is not None else self._wait_ms
        if delay > 0:
            await asyncio.sleep(delay / 1000)

    @property
    def pw(self) -> PwPage:
        """Access the underlying Playwright page for advanced usage."""
        return self._page
