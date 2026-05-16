"""Tests for executor callback hooks (on_before/on_after scenario)."""

from pathlib import Path

import pytest

from scout.runner.executor import execute_batch


@pytest.fixture
def scenario_file(tmp_path: Path) -> Path:
    """Create a minimal passing test.py scenario."""
    scenarios = tmp_path / "scenarios" / "demo" / "test-ok"
    scenarios.mkdir(parents=True)
    (tmp_path / "app.json").write_text('{"name":"test","web_base_url":"http://localhost"}')
    test_py = scenarios / "test.py"
    test_py.write_text(
        "from scout.runner import Scenario, Page\n"
        'scenario = Scenario(name="test", base_url="http://localhost")\n'
        "@scenario.test\n"
        "async def test(page: Page):\n"
        "    pass\n"
    )
    return test_py


@pytest.mark.e2e
async def test_callbacks_called_in_order(scenario_file: Path) -> None:
    """on_before and on_after callbacks are called around each scenario."""
    calls: list[str] = []

    async def before(scenario_path: str) -> None:
        calls.append(f"before:{scenario_path}")

    async def after(scenario_path: str, result) -> None:
        calls.append(f"after:{scenario_path}:{result.success}")

    results = await execute_batch(
        [str(scenario_file)],
        headless=True,
        on_before_scenario=before,
        on_after_scenario=after,
    )

    assert len(results) == 1
    assert calls == ["before:demo/test-ok", "after:demo/test-ok:True"]
