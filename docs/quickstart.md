# Quickstart

This walks through installing scout and running your first cross-version
diff against a local app.

## Install

```bash
pip install boxprobe-scout
playwright install chromium
```

scout requires Python ≥ 3.11.

## Project layout

A scout project is a directory containing `app.json` plus a `scenarios/`
tree:

```
my-app/
├── app.json
├── diff_ignore.json        # optional — noise rules
└── scenarios/
    └── login/
        └── test.py
```

### `app.json`

```json
{
  "name": "my-app",
  "web_base_url": "https://app.example.com",
  "api_base_url": "https://api.example.com",
  "viewport_width": 1280,
  "viewport_height": 800,
  "variables": {
    "admin_user": "admin@example.com",
    "admin_pass": "your-password"
  }
}
```

`web_base_url` is what your scenarios navigate against. `api_base_url`
tells scout's recording proxy which traffic counts as "your API" (and
therefore gets diffed) vs traffic to third-party services (which is
ignored).

### A scenario

```python
# scenarios/login/test.py
from scout.runner import Locator, Page, Scenario

scenario = Scenario(
    name="login",
    base_url="https://app.example.com",
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

`bbox=(x, y, w, h)` is the element's bounding box at recording time, in
viewport coordinates. See [Scenarios](scenarios.md) for the full
`Locator` API including relative positioning and dynamic-size flags.

## Run it

```bash
# Baseline
scout run scenarios/ --web-version 1.0.0

# Deploy your app to a new version, then:
scout run scenarios/ --web-version 1.1.0

# List both runs
scout runs

# Diff them
scout diff <baseline-run-id> <target-run-id>
```

The `scout diff` command opens an HTML report in your browser grouped by
endpoint, with structural and value diffs side by side.

## What's recorded where

```
.scout/
├── index.db                          # All run metadata (queryable)
├── runs/
│   └── <run-id>/
│       ├── record.db                 # Per-scenario API traffic
│       ├── <scenario-path>/
│       │   └── result.json           # Pass/fail + duration + errors
│       ├── report.html               # Per-run HTML execution report
│       └── junit.xml                 # CI integration
└── diffs/
    └── <baseline>_vs_<target>/
        ├── diff.db                   # Pairings + comparisons
        └── report.html               # The diff report you opened
```

All of this stays on the machine running scout. No upload, no telemetry.

## Next steps

- [Diff ignore rules](diff-ignore.md) — write your first noise suppression
  rules so the report surfaces real changes, not timestamps
- [Scenarios](scenarios.md) — `Locator` API for relative positioning,
  dynamic dimensions, filtered child elements
- [CLI reference](cli.md) — `verify` mode for debugging, URL overrides,
  scenario filtering
