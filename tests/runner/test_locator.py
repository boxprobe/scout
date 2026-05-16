"""Tests for scout.runner.locator — coordinate resolution logic."""

from scout.runner.locator import Locator


def test_locator_center_abs():
    """Absolute locator resolves to bbox center, adjusted for scroll."""
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


def test_locator_resolve_static_abs():
    """Static resolution for abs sets _resolved_bbox."""
    loc = Locator(name="btn", tag="button", bbox=(100, 200, 60, 40))
    result = loc.resolve_static({})
    assert result == {"x": 100, "y": 200, "w": 60, "h": 40}
    assert loc.resolved


def test_locator_resolve_static_dxy():
    """dxy locator computes position from parent + dx/dy offsets."""
    parent = Locator(name="container", tag="div", bbox=(50, 100, 400, 300))
    child = Locator(
        name="inner-btn",
        tag="button",
        bbox=(0, 0, 80, 30),
        pos_type="dxy",
        parent="container",
        pos_offset={"dx": 20, "dy": 50},
    )
    registry = {"container": parent, "inner-btn": child}
    result = child.resolve_static(registry)
    assert result == {"x": 70, "y": 150, "w": 80, "h": 30}


def test_locator_resolve_static_rel_left_top():
    """rel locator with left/top offsets from parent."""
    parent = Locator(name="panel", tag="div", bbox=(100, 200, 500, 400))
    child = Locator(
        name="label",
        tag="span",
        bbox=(0, 0, 60, 20),
        pos_type="rel",
        parent="panel",
        pos_offset={"left": 10, "top": 5},
    )
    registry = {"panel": parent, "label": child}
    result = child.resolve_static(registry)
    assert result == {"x": 110, "y": 205, "w": 60, "h": 20}


def test_locator_resolve_static_rel_right_bottom():
    """rel locator with right/bottom offsets from parent."""
    parent = Locator(name="panel", tag="div", bbox=(100, 200, 500, 400))
    child = Locator(
        name="close-btn",
        tag="button",
        bbox=(0, 0, 30, 30),
        pos_type="rel",
        parent="panel",
        pos_offset={"right": 10, "bottom": 10},
    )
    registry = {"panel": parent, "close-btn": child}
    result = child.resolve_static(registry)
    # x = 100 + 500 - 10 - 30 = 560
    # y = 200 + 400 - 10 - 30 = 560
    assert result == {"x": 560, "y": 560, "w": 30, "h": 30}


def test_locator_resolve_static_missing_parent():
    """Missing parent falls back to raw bbox."""
    child = Locator(
        name="orphan",
        tag="div",
        bbox=(10, 20, 30, 40),
        pos_type="rel",
        parent="nonexistent",
    )
    result = child.resolve_static({})
    assert result == {"x": 10, "y": 20, "w": 30, "h": 40}


def test_locator_center_after_resolve():
    """Center uses resolved bbox when available."""
    parent = Locator(name="form", tag="form", bbox=(100, 200, 400, 300))
    child = Locator(
        name="submit",
        tag="button",
        bbox=(0, 0, 80, 40),
        pos_type="dxy",
        parent="form",
        pos_offset={"dx": 160, "dy": 250},
    )
    registry = {"form": parent, "submit": child}
    child.resolve_static(registry)
    x, y = child.center()
    # resolved: x=260, y=450, w=80, h=40 → center (300, 470)
    assert x == 300
    assert y == 470


def test_locator_repr():
    """Repr shows name and bbox for debugging."""
    loc = Locator(name="email", tag="input", bbox=(10, 20, 200, 30))
    assert "email" in repr(loc)
    assert "10" in repr(loc)


def test_locator_repr_rel():
    """Repr for rel locator shows pos_type and parent."""
    loc = Locator(
        name="btn",
        tag="button",
        bbox=(0, 0, 50, 30),
        pos_type="rel",
        parent="container",
    )
    r = repr(loc)
    assert "rel" in r
    assert "container" in r
