# scout

UI-driven API regression testing — a CLI that executes pre-recorded
scenarios, captures API traffic via a proxy, and produces cross-version
diff reports.

**Install:**

```bash
pip install boxprobe-scout
playwright install chromium
```

## Code structure

```
scout/
├── cli.py                  # Click CLI entry
│                           #   scout run    — record API traffic during execution
│                           #   scout verify — screenshot mode for scenario debugging
│                           #   scout diff   — compare two runs' API recordings
│                           #   scout runs   — list run history
├── config.py               # app.json loader + URL overrides
├── git.py                  # git commit/branch lookup for run metadata
├── index.py                # local run index (SQLite, .scout/index.db)
├── run_metadata.py         # run metadata assembly
├── runner/
│   ├── executor.py         # Playwright orchestration, batch execution
│   ├── scenario.py         # Scenario DSL (base_url, @setup, @test)
│   ├── page.py             # Page wrapper (goto/click/fill/wait via Locator)
│   └── locator.py          # Pixel-anchored Locator with abs/rel/dxy positioning
├── collector/
│   ├── subprocess.py       # recording proxy subprocess manager
│   ├── proxy.py            # mitmproxy addon
│   ├── control.py          # proxy control API (session start/stop)
│   └── db.py               # recording DB (SQLite: scenarios + api_records)
├── matcher/
│   ├── align.py            # endpoint pairing (path-only + 2-stage query match)
│   ├── compare.py          # JSON structure + value comparison
│   ├── normalize.py        # URL path normalization (dynamic ID inference)
│   ├── noise.py            # diff_ignore.json rules + known-change suppression
│   ├── diff_db.py          # diff result DB
│   └── diff_report.py      # HTML diff report generation
├── report/
│   ├── html.py             # per-run HTML report
│   └── junit.py            # JUnit XML report
├── secrets/                # credential injection (pyrage encryption — planned)
├── bridge/                 # browser bridge over CDP — planned
├── mcp/                    # MCP server for AI agent integration — planned
└── server/                 # planned
```

## CLI commands

```bash
# Recording run: launches proxy, records API traffic to
# .scout/runs/<run_id>/record.db
scout run scenarios/auth/login-success --web-version 1.0.0
scout run scenarios/ --web-version 1.0.0   # recurse: find any test.py

# Debug verify: screenshot mode, no proxy
scout verify scenarios/auth/login-success --headed

# Diff: compare two recordings
scout runs                                  # list run IDs
scout diff <baseline-id> <target-id>
scout diff <baseline-id> <target-id> --no-detail  # skip body popup data

# URL override (for staging/local environments)
scout run scenarios/ --web-base-url http://localhost:9000 \
                     --api-base-url http://localhost:9000 \
                     --web-version dev
```

`--web-version` is required on `scout run` — it tags the recording so
diff reports can label each side and so "added in <ver>" known-change
buttons in the report work correctly.

## Data flow

```
scout run
  ├── Launch recording proxy (separate process)
  ├── Playwright browser → proxy → target app
  ├── Notify proxy of session boundaries per scenario
  ├── API traffic     → .scout/runs/<run_id>/record.db
  ├── Per-scenario    → .scout/runs/<run_id>/<scenario>/result.json
  ├── HTML+JUnit      → .scout/runs/<run_id>/report.html, junit.xml
  └── Run index       → .scout/index.db

scout diff baseline target
  ├── Read both runs' record.db
  ├── Pair endpoints by path; resolve query differences (2-stage)
  ├── Compare status code + JSON structure + values
  ├── Apply diff_ignore.json rules (field/value-type/endpoint ignores)
  ├── Diff DB         → .scout/diffs/<baseline>_vs_<target>/diff.db
  └── HTML report     → .scout/diffs/<baseline>_vs_<target>/report.html
```

## Scenario file format

A scenario lives in a directory next to an `app.json`:

```
my-app/
├── app.json
├── diff_ignore.json        # optional: noise rules
└── scenarios/
    └── login/
        └── test.py
```

```json
// app.json
{
  "name": "my-app",
  "web_base_url": "https://app.example.com",
  "api_base_url": "https://api.example.com",
  "viewport_width": 1280,
  "viewport_height": 800
}
```

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

## Tech stack

| Layer              | Choice                                    |
|--------------------|-------------------------------------------|
| CLI                | Python + Click                            |
| Browser automation | Playwright (Python)                       |
| HTTP client        | httpx                                     |
| Recording proxy    | mitmproxy (separate process)              |
| Data store         | SQLite (recordings, diffs, run index)     |
| Reports            | HTML + JUnit XML                          |
| Lint + format      | ruff                                      |
| Type checking      | pyright                                   |
| Tests              | pytest + pytest-asyncio + pytest-playwright |

## Python environment

- Python >= 3.11
- Uses [uv](https://docs.astral.sh/uv/) for environment management
- **All Python commands must use `uv run`** — never bare `python` or `pip`.
  `uv run` guarantees the venv interpreter matches `pyproject.toml`'s
  `requires-python`; system Python can silently drift.

## Conventions

- Code, comments, commit messages, issues, PRs: English
- [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`,
  `fix:`, `test:`, `refactor:`, `docs:`, `chore:`
- Run `uv run pytest tests/ -x --tb=short -m "not e2e"` before pushing
- See [CONTRIBUTING.md](CONTRIBUTING.md) for full development setup
