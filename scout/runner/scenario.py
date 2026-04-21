"""Scenario — test configuration and lifecycle management.

A generated test.py creates a Scenario instance, registers setup/test
functions via decorators, then calls scenario.run() as the entry point.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scout.runner.page import Page

    AsyncPageFn = Callable[[Page], Coroutine[Any, Any, None]]


class Scenario:
    """Holds scenario config and registered setup/test functions."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        viewport_width: int = 1280,
        wait_ms: int = 0,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.viewport_width = viewport_width
        self.wait_ms = wait_ms
        self._setup_fn: AsyncPageFn | None = None
        self._test_fn: AsyncPageFn | None = None

    def setup(self, fn: AsyncPageFn) -> AsyncPageFn:
        """Decorator: register the setup function."""
        self._setup_fn = fn
        return fn

    def test(self, fn: AsyncPageFn) -> AsyncPageFn:
        """Decorator: register the test function."""
        self._test_fn = fn
        return fn

    def _validate(self) -> None:
        if self._test_fn is None:
            raise RuntimeError(f"No test function registered for scenario '{self.name}'")

    def run(self) -> None:
        """Sync entry point — launches the executor."""
        self._validate()
        from scout.runner.executor import execute_scenario

        asyncio.run(execute_scenario(self, headless=True))
