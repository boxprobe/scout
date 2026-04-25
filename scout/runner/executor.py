"""Executor — launches Playwright and runs Scenarios.

This module is the bridge between the Scenario/Page abstractions and
the Playwright browser. It handles browser lifecycle, viewport setup,
and error capture. Supports both single-file and batch execution.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from scout.runner.page import Page
from scout.runner.scenario import Scenario


@dataclass
class ExecutionResult:
    """Result of running a scenario."""

    success: bool
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0


def _load_scenario(test_path: Path) -> Scenario | ExecutionResult:
    """Import a test.py file and extract its scenario object.

    Returns Scenario on success, ExecutionResult on failure.
    """
    if not test_path.exists():
        return ExecutionResult(success=False, errors=[f"File not found: {test_path}"])

    try:
        spec = importlib.util.spec_from_file_location("_scout_test", test_path)
        if spec is None or spec.loader is None:
            return ExecutionResult(success=False, errors=[f"Cannot load: {test_path}"])

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        scenario = getattr(module, "scenario", None)
        if scenario is None:
            return ExecutionResult(
                success=False,
                errors=["test.py must define a module-level 'scenario' variable"],
            )
        return scenario
    except Exception as exc:
        return ExecutionResult(success=False, errors=[f"Import error: {exc}"])


async def _run_scenario_with_browser(
    scenario: Scenario,
    browser: Any,
    *,
    screenshot_dir: Path | None = None,
) -> ExecutionResult:
    """Execute a scenario using an existing browser instance."""
    scenario._validate()

    context = await browser.new_context(
        viewport={"width": scenario.viewport_width, "height": scenario.viewport_height},
    )
    pw_page = await context.new_page()
    page = Page(
        pw_page,
        base_url=scenario.base_url,
        wait_ms=scenario.wait_ms,
        screenshot_dir=screenshot_dir,
    )

    t0 = time.monotonic()
    try:
        if scenario._setup_fn:
            await scenario._setup_fn(page)
        await scenario._test_fn(page)  # type: ignore[misc]
        # Final screenshot — capture end state after all steps + waits
        if screenshot_dir is not None:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            await pw_page.screenshot(
                path=screenshot_dir / "final.png",
            )
        duration = int((time.monotonic() - t0) * 1000)
        return ExecutionResult(success=True, duration_ms=duration)
    except Exception as exc:
        duration = int((time.monotonic() - t0) * 1000)
        # Capture error state screenshot
        if screenshot_dir is not None:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            await pw_page.screenshot(
                path=screenshot_dir / "error.png",
            )
        return ExecutionResult(success=False, errors=[str(exc)], duration_ms=duration)
    finally:
        await context.close()


async def execute_scenario(scenario: Scenario, *, headless: bool = True) -> ExecutionResult:
    """Execute a scenario: launch browser → setup → test → close."""
    scenario._validate()

    pw_instance = await async_playwright().start()
    browser = await pw_instance.chromium.launch(headless=headless)

    try:
        return await _run_scenario_with_browser(scenario, browser)
    finally:
        await browser.close()
        await pw_instance.stop()


async def execute_file(test_path: str | object, *, headless: bool = True) -> ExecutionResult:
    """Execute a single generated test.py file."""
    path = Path(str(test_path))
    loaded = _load_scenario(path)
    if isinstance(loaded, ExecutionResult):
        return loaded
    return await execute_scenario(loaded, headless=headless)


def _scout_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("scout")
    except PackageNotFoundError:
        return "dev"


def _result_to_dict(result: ExecutionResult) -> dict[str, Any]:
    """Convert ExecutionResult to a JSON-serializable dict."""
    return {
        "success": result.success,
        "errors": result.errors,
        "duration_ms": result.duration_ms,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scout_version": _scout_version(),
    }


def _derive_scenario_path(test_path: Path) -> str:
    """Derive scenario path from test.py location.

    Walks up from the test.py file looking for a 'scenarios' parent directory.
    E.g. .../scenarios/auth/login-success/test.py → auth/login-success
    """
    parts = test_path.resolve().parts
    for i, part in enumerate(parts):
        if part == "scenarios" and i + 1 < len(parts):
            # Everything between 'scenarios/' and 'test.py'
            scenario_parts = parts[i + 1 : -1]  # exclude 'test.py' filename
            if scenario_parts:
                return "/".join(scenario_parts)
    # Fallback: use stem of parent directory
    return test_path.parent.name


def _find_worktree_root(test_path: Path) -> Path | None:
    """Walk up from test.py looking for app.json (worktree root marker)."""
    current = test_path.resolve().parent
    while current != current.parent:
        if (current / "app.json").exists():
            return current
        current = current.parent
    return None


async def execute_batch(
    test_paths: list[str],
    *,
    headless: bool = True,
    results_dir: Path | None = None,
    screenshots: bool = False,
    proxy: str | None = None,
    on_before_scenario: Callable | None = None,
    on_after_scenario: Callable | None = None,
    base_url_override: str | None = None,
) -> dict[str, ExecutionResult]:
    """Execute multiple test.py files sharing one browser instance.

    Results are written to results_dir as individual JSON files.
    When screenshots=True, before/after screenshots are saved per scenario.
    Returns a dict mapping scenario_path → ExecutionResult.
    """
    # Load all scenarios first (fail fast on import errors)
    entries: list[tuple[str, Scenario | ExecutionResult]] = []
    for tp in test_paths:
        path = Path(tp)
        scenario_path = _derive_scenario_path(path)
        loaded = _load_scenario(path)
        entries.append((scenario_path, loaded))

    # Clean previous results for each scenario to avoid stale artifacts
    if results_dir is not None:
        for scenario_path, _ in entries:
            scenario_dir = results_dir / scenario_path
            if scenario_dir.exists():
                shutil.rmtree(scenario_dir)

    results: dict[str, ExecutionResult] = {}

    # Launch one browser for the entire batch
    pw_instance = await async_playwright().start()
    browser = await pw_instance.chromium.launch(
        headless=headless,
        proxy={"server": f"http://{proxy}"} if proxy else None,
    )

    try:
        for scenario_path, loaded in entries:
            if isinstance(loaded, ExecutionResult):
                results[scenario_path] = loaded
            else:
                if base_url_override:
                    loaded.base_url = base_url_override
                if on_before_scenario:
                    await on_before_scenario(scenario_path)
                ss_dir = None
                if screenshots and results_dir is not None:
                    ss_dir = results_dir / scenario_path / "screenshots"
                result = await _run_scenario_with_browser(
                    loaded, browser, screenshot_dir=ss_dir
                )
                results[scenario_path] = result
                if on_after_scenario:
                    await on_after_scenario(scenario_path, result)
    finally:
        await browser.close()
        await pw_instance.stop()

    # Write results to disk — each scenario gets its own directory
    if results_dir is not None:
        for scenario_path, result in results.items():
            scenario_dir = results_dir / scenario_path
            scenario_dir.mkdir(parents=True, exist_ok=True)
            (scenario_dir / "result.json").write_text(
                json.dumps(_result_to_dict(result), indent=2) + "\n",
                encoding="utf-8",
            )

    return results
