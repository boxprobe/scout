"""Executor — launches Playwright and runs a Scenario.

This module is the bridge between the Scenario/Page abstractions and
the Playwright browser. It handles browser lifecycle, viewport setup,
and error capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright

from scout.runner.page import Page
from scout.runner.scenario import Scenario


@dataclass
class ExecutionResult:
    """Result of running a scenario."""

    success: bool
    errors: list[str] = field(default_factory=list)


async def _launch_browser(
    headless: bool, viewport_width: int
) -> tuple[Any, Any, Any]:
    """Start Chromium and create a page with the specified viewport.

    Returns (playwright_instance, browser, page) — caller must close all three.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    context = await browser.new_context(
        viewport={"width": viewport_width, "height": 900},
    )
    page = await context.new_page()
    return pw, browser, page


async def execute_scenario(scenario: Scenario, *, headless: bool = True) -> ExecutionResult:
    """Execute a scenario: launch browser → setup → test → close.

    Returns an ExecutionResult with success status and any error messages.
    """
    scenario._validate()

    pw_instance, browser, pw_page = await _launch_browser(headless, scenario.viewport_width)
    page = Page(pw_page, base_url=scenario.base_url, wait_ms=scenario.wait_ms)

    try:
        if scenario._setup_fn:
            await scenario._setup_fn(page)

        await scenario._test_fn(page)  # type: ignore[misc]

        return ExecutionResult(success=True)
    except Exception as exc:
        return ExecutionResult(success=False, errors=[str(exc)])
    finally:
        await browser.close()
        await pw_instance.stop()


async def execute_file(test_path: str | object, *, headless: bool = True) -> ExecutionResult:
    """Execute a generated test.py file by importing it and running its scenario.

    The file must define a module-level `scenario` variable of type Scenario.
    """
    import importlib.util
    from pathlib import Path

    path = Path(str(test_path))
    if not path.exists():  # noqa: ASYNC240
        return ExecutionResult(success=False, errors=[f"File not found: {path}"])

    try:
        spec = importlib.util.spec_from_file_location("_scout_test", path)
        if spec is None or spec.loader is None:
            return ExecutionResult(success=False, errors=[f"Cannot load: {path}"])

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        scenario = getattr(module, "scenario", None)
        if scenario is None:
            return ExecutionResult(
                success=False,
                errors=["test.py must define a module-level 'scenario' variable"],
            )

        return await execute_scenario(scenario, headless=headless)
    except Exception as exc:
        return ExecutionResult(success=False, errors=[f"Import/execution error: {exc}"])
