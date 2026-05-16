# Scenarios

A scenario is a Python file that declares a `Scenario` object, registers
a test function via the `@scenario.test` decorator, and (optionally)
declares `Locator` objects for elements the test interacts with.

```python
from scout.runner import Locator, Page, Scenario

scenario = Scenario(
    name="login",
    base_url="https://app.example.com",
)

email = Locator(name="email", tag="input", bbox=(640, 320, 280, 32))
submit = Locator(name="submit", tag="button", bbox=(640, 428, 280, 40))


@scenario.test
async def test(page: Page) -> None:
    await page.goto("/login")
    await page.fill(email, "user@example.com")
    await page.click(submit)
```

---

## `Scenario`

```python
Scenario(
    *,
    name: str,
    base_url: str,
    viewport_width: int = 1280,
    viewport_height: int = 900,
    wait_ms: int = 0,
)
```

| Parameter | Description |
|---|---|
| `name` | Human-readable scenario identifier (recorded with each run) |
| `base_url` | URL the scenario navigates against. Overridden by `scout run --web-base-url` |
| `viewport_width` / `viewport_height` | Browser viewport size — must match the size used at recording time (Locator bboxes are viewport-relative) |
| `wait_ms` | Default wait after each action, in milliseconds. Useful for SPA route transitions. Per-call `page.wait()` overrides |

### Decorators

- `@scenario.setup` — runs once before `@scenario.test`. Use for login, fixture setup, navigation to a starting page
- `@scenario.test` — the actual test logic. Required

```python
@scenario.setup
async def setup(page: Page) -> None:
    await page.goto("/login")
    await page.fill(email, "...")
    await page.click(submit)

@scenario.test
async def test(page: Page) -> None:
    await page.goto("/dashboard")
    # ...
```

---

## `Locator`

```python
Locator(
    *,
    name: str,
    tag: str,
    bbox: tuple[int, int, int, int],
    scroll_y: int = 0,
    pos_type: str = "abs",
    parent: str | None = None,
    pos_offset: dict | None = None,
    dynamic: dict | None = None,
    filter: str | None = None,
)
```

| Parameter | Description |
|---|---|
| `name` | Identifier for logging — also appears in the diff report |
| `tag` | Expected HTML tag (`button`, `input`, `a`, ...). Used to disambiguate when multiple elements occupy similar coordinates |
| `bbox` | `(x, y, width, height)` in viewport coordinates, captured at recording time |
| `scroll_y` | Page scroll offset at recording time. scout scrolls back to this position before resolving the element |
| `pos_type` | `"abs"` (default), `"rel"`, or `"dxy"`. See **Positioning modes** below |
| `parent` | Name of the parent Locator (for `rel` / `dxy` modes) |
| `pos_offset` | Offset specification — `{"left": N, "top": N}` for `rel`, `{"dx": N, "dy": N}` for `dxy` |
| `dynamic` | `{"w": bool, "h": bool}` — flag width/height as dynamic; scout re-resolves at runtime |
| `filter` | CSS or XPath selector to narrow the bbox to a specific child element |

### Positioning modes

**`abs` (absolute)** — bbox is in viewport coordinates. The element is
expected at exactly that position relative to the viewport top-left.

```python
submit = Locator(
    name="submit", tag="button",
    bbox=(640, 428, 280, 40),  # viewport-relative
)
```

**`rel` (relative-to-parent)** — bbox is relative to the parent
Locator's bbox, anchored by `pos_offset`. Use when a child element is
laid out by container offset (e.g., a dropdown menu item relative to its
trigger button).

```python
menu = Locator(name="menu", tag="div", bbox=(800, 100, 200, 300))
item = Locator(
    name="menu-item", tag="a",
    bbox=(810, 140, 180, 36),
    pos_type="rel",
    parent="menu",
    pos_offset={"left": 10, "top": 40},  # offset from menu top-left
)
```

**`dxy` (delta from parent center)** — bbox positioned by pixel delta
from parent's center. Useful for cluster-positioned elements.

```python
chip = Locator(
    name="chip", tag="span",
    bbox=(0, 0, 60, 24),
    pos_type="dxy",
    parent="cluster",
    pos_offset={"dx": -40, "dy": 0},
)
```

### Dynamic dimensions

Width or height of an element changes between runs (variable-length text,
expandable panels). Flag the dimension to make scout re-measure at
runtime:

```python
text_block = Locator(
    name="status-text", tag="div",
    bbox=(100, 200, 400, 24),
    dynamic={"w": True, "h": True},  # both dimensions re-resolved
)
```

### Filter

When the bbox covers a region but you want a specific child element,
narrow with a CSS or XPath selector:

```python
row = Locator(
    name="user-row", tag="tr",
    bbox=(0, 100, 1200, 48),
    filter="button.delete",  # CSS: pick the delete button inside this row
)
```

---

## `Page`

The `Page` object wraps a Playwright page with Locator-aware actions.
It's passed into your `setup` and `test` functions.

| Method | What it does |
|---|---|
| `await page.goto(url)` | Navigate (relative to `base_url`) |
| `await page.click(locator)` | Resolve Locator and click |
| `await page.fill(locator, value)` | Resolve Locator and fill text |
| `await page.select_option(locator, value)` | Resolve `<select>` and pick option by value |
| `await page.hover(locator)` | Resolve Locator and hover |
| `await page.wait(ms=None)` | Wait `ms` milliseconds (or `scenario.wait_ms` if `None`) |
| `page.pw()` | Escape hatch — return the underlying Playwright `Page` for advanced needs |

All actions take screenshots before/after, captured under
`.scout/runs/<run-id>/<scenario>/screenshots/`. The "before" screenshot
also draws the resolved bbox so you can see where scout aimed.
