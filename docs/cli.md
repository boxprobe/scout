# CLI reference

```
scout [OPTIONS] COMMAND [ARGS]...
```

scout has seven subcommands. Four are fully implemented for v0.1; three
are planned and reserved (`upload`, `analyze`, `report`).

---

## `scout run`

Execute scenarios against a target app, recording all API traffic.

```
scout run <PATHS...> [OPTIONS]
```

### Required

| Option | Description |
|---|---|
| `--web-version TEXT` | Version label for the web app being tested (e.g. `2.14.0`). Tags the recording so diff reports can identify which deployed version produced each side |

### Common options

| Option | Default | Description |
|---|---|---|
| `--headless/--headed` | headless | Run browser headless (CI) or with a visible window (debug) |
| `--web-base-url URL` | `app.json.web_base_url` | Override target URL |
| `--api-base-url URL` | `app.json.api_base_url` | Override API URL (what the recording proxy considers "your API" vs third-party traffic) |
| `--api-version TEXT` | `--web-version` value | Tag API version separately if it differs from web version |
| `--web-commit SHA` | (none) | Record web app commit hash |
| `--api-commit SHA` | (none) | Record API commit hash |
| `--env NAME` | (none) | Environment label (`staging`, `prod`, `local`) |
| `--out DIR` | `.scout/runs/` | Where to write run output |

### Examples

```bash
# Single scenario
scout run scenarios/auth/login --web-version 2.14.0

# Whole directory tree (recurse find test.py)
scout run scenarios/ --web-version 2.14.0

# Against a different target version on different port
scout run scenarios/ --web-version 2.14.0 \
                     --web-base-url http://localhost:29000/app \
                     --api-base-url http://localhost:29000
```

---

## `scout verify`

Debug mode — execute scenarios without launching the recording proxy.
Captures screenshots and Locator-resolution data for inspection. Use when
a scenario is failing and you want to see what scout actually did.

```
scout verify <PATHS...> [--headed]
```

`--headed` opens a visible browser so you can watch the run.

Output goes under `.scout/verify/<scenario>/`:

- `screenshots/before-N.png`, `after-N.png` — per-action snapshots, with
  the resolved bbox drawn on `before`
- `result.json` — pass/fail + error trace + resolved bbox values per
  Locator

---

## `scout diff`

Compare two recorded runs and produce an HTML diff report.

```
scout diff <BASELINE_RUN_ID> <TARGET_RUN_ID> [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--detail/--no-detail` | detail | Include raw request/response bodies in the report (needed for popup body diffs) |
| `--out DIR` | `.scout/diffs/` | Where to write the diff report |

The command opens the resulting HTML report in your browser.

### Examples

```bash
# Last two runs (use `scout runs` to grab IDs)
scout diff 20260516-103012-a1b2 20260516-104530-c3d4

# Minimal report — drops body bodies, faster generation
scout diff 20260516-103012-a1b2 20260516-104530-c3d4 --no-detail
```

---

## `scout runs`

List recorded runs from the local index.

```
scout runs [--app NAME] [--env NAME] [--limit N]
```

Output is a table of run-id × app × version × env × duration. Useful for
grabbing IDs to pass to `scout diff`.

---

## `scout report`

Regenerate the HTML diff report for a previously computed diff (e.g.,
after editing `diff_ignore.json` and wanting to re-apply rules without
re-running scenarios).

```
scout report <DIFF_ID>
```

**Status: planned.** Not yet implemented as of v0.1.

---

## `scout upload`

Upload run / diff data to object storage (S3-compatible). Designed for
sharing diff reports with reviewers who don't have local access.

**Status: planned.** Not yet implemented as of v0.1.

---

## `scout analyze`

Run additional analyses on diff data — anomaly detection, statistical
summaries, regression severity classification.

**Status: planned.** Not yet implemented as of v0.1.

---

## Global options

| Option | Description |
|---|---|
| `--version` | Print scout version and exit |
| `--help` | Print help for the current command |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All scenarios passed / diff report generated successfully |
| 1 | One or more scenarios failed during execution |
| 2 | CLI argument error |
| 3 | Recording proxy failed to start |
