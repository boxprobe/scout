# scout

**UI-driven API regression testing.** Maintained by [BoxProbe](https://boxprobe.com).

[![PyPI](https://img.shields.io/pypi/v/boxprobe-scout.svg)](https://pypi.org/project/boxprobe-scout/)
[![Python](https://img.shields.io/pypi/pyversions/boxprobe-scout.svg)](https://pypi.org/project/boxprobe-scout/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

scout drives your web app's UI like a real user, records the resulting API
traffic, and produces a diff report between two runs. When a deploy silently
changes a response shape, scout tells you which endpoint changed, in which
user flow, and exactly how.

It is **not** a contract testing tool — there's no OpenAPI spec to maintain. You
record what your UI actually triggers, and the test fails when the same clicks
produce different bytes against a new version of your backend.

---

## Why scout

- **Pixel-precise element location.** Scenarios reference elements by
  annotation-time bounding boxes, not CSS selectors. Refactoring class names
  doesn't break tests.
- **Deterministic replay.** Scenarios are plain Python — no AI tokens consumed
  at runtime, no LLM in the hot path. Same input, same trace.
- **Real cross-version diff.** Run against `v1.0`, run against `v1.1`,
  `scout diff` produces an HTML report grouping changes by endpoint and user
  flow. Surface real regressions, not selector breakage.
- **Honest scope.** scout doesn't try to be your unit test runner or your
  load testing tool. It catches one specific class of bug: API behavior drift
  that survives your existing tests because it only manifests through real UI
  interaction.

---

## Install

```bash
pip install boxprobe-scout
playwright install chromium
```

Requires Python ≥ 3.11.

---

## Quickstart

A scenario is a Python file declaring locators and an async test function:

```python
# scenarios/login/test.py
from scout.runner import Locator, Page, Scenario

scenario = Scenario(
    name="login",
    base_url="https://your-app.example.com",
    viewport_width=1280,
    viewport_height=800,
)

email = Locator(name="email", tag="input", bbox=(640, 320, 280, 32))
password = Locator(name="password", tag="input", bbox=(640, 372, 280, 32))
submit = Locator(name="submit", tag="button", bbox=(640, 428, 280, 40))


@scenario.test
async def test(page: Page) -> None:
    await page.goto("/login")
    await page.fill(email, "user@example.com")
    await page.fill(password, "password123")
    await page.click(submit)
    await page.wait(2000)


if __name__ == "__main__":
    scenario.run()
```

Run it once against your baseline, then again against the target version:

```bash
scout run scenarios/              # records API traffic, stores under .scout/runs/
scout run scenarios/              # second run after deploy

scout runs                        # list run IDs
scout diff <baseline-id> <target-id>
```

scout opens an HTML report grouped by endpoint, with structural and value
diffs side-by-side.

---

## How it works

```
scout run
  └── Playwright browser → recording proxy → your app
                                 │
                                 └── API traffic → .scout/runs/<id>/record.db

scout diff baseline target
  └── Pair endpoints by path + structural query → diff status + JSON shape + values
                                 │
                                 └── HTML report grouped by user flow + endpoint
```

The recording proxy is a separate Rust binary (`hudsucker`) launched as a
subprocess. Tests run headless by default; pass `scout verify` for a debug
mode with screenshots and no proxy.

---

## Status

scout is **alpha** (`0.1.x`). The CLI surface and scenario DSL are stabilizing;
expect breaking changes between minor versions until `1.0`. Production-quality
diff reports and stable file formats are the v1.0 bar.

What works today:

- Pixel-anchored locators with absolute, relative, and delta-from-parent
  positioning modes
- Recording proxy + per-scenario API capture
- Structural and value diffs with known-change suppression via
  `diff_ignore.json`
- HTML diff report with filterable endpoint table

What's coming:

- npm-distributable wrapper for TS projects
- GitHub Action template for CI
- MCP server for AI agent integration

---

## Authoring scenarios

Hand-writing locators with pixel coordinates is possible but tedious. The
scenario file format is open and stable enough to target with your own
recording tooling — point a browser-extension or annotation pipeline at it
and emit `test.py` files in the format above.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome; please open an issue first
for non-trivial changes.

---

## License

MIT — see [LICENSE](LICENSE).
