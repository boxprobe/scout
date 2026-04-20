"""Tests for scout.runner.scenario — config holder + decorator registration."""

import pytest

from scout.runner.scenario import Scenario


def test_scenario_config():
    """Scenario stores configuration."""
    s = Scenario(name="auth.login", base_url="https://example.com", viewport_width=1280)
    assert s.name == "auth.login"
    assert s.base_url == "https://example.com"
    assert s.viewport_width == 1280
    assert s.wait_ms == 0


def test_scenario_setup_decorator():
    """@scenario.setup registers the setup function."""
    s = Scenario(name="test", base_url="http://localhost")

    @s.setup
    async def my_setup(page):
        pass

    assert s._setup_fn is my_setup


def test_scenario_test_decorator():
    """@scenario.test registers the test function."""
    s = Scenario(name="test", base_url="http://localhost")

    @s.test
    async def my_test(page):
        pass

    assert s._test_fn is my_test


def test_scenario_test_required():
    """_validate() without a registered test raises."""
    s = Scenario(name="test", base_url="http://localhost")
    with pytest.raises(RuntimeError, match="No test function registered"):
        s._validate()
