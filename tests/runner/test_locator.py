"""Tests for scout.runner.locator — annotation data holder + coordinate resolution."""

from scout.runner.locator import Locator


def test_locator_center_abs():
    """Absolute locator resolves to bbox center."""
    loc = Locator(name="login-btn", tag="button", bbox=(100, 200, 60, 40))
    x, y = loc.center()
    assert x == 130  # 100 + 60/2
    assert y == 220  # 200 + 40/2


def test_locator_center_with_scroll():
    """Scroll offset subtracts from y."""
    loc = Locator(name="footer", tag="div", bbox=(0, 800, 100, 50), scroll_y=500)
    x, y = loc.center()
    assert x == 50
    assert y == 325  # (800 - 500) + 50/2


def test_locator_repr():
    """Repr shows name and bbox for debugging."""
    loc = Locator(name="email", tag="input", bbox=(10, 20, 200, 30))
    assert "email" in repr(loc)
    assert "10" in repr(loc)
