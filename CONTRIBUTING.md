# Contributing to scout

Thanks for considering a contribution. scout is alpha and the API is still
moving, so please open an issue before non-trivial work to make sure your
direction matches the project's.

## Reporting bugs

Open an issue with:

- scout version (`scout --version` or `pip show boxprobe-scout`)
- Python version (`python --version`)
- OS and architecture
- Minimal reproduction: a scenario file or CLI invocation that produces the
  failure
- What you expected vs. what happened
- Full traceback if there is one

Attach `.scout/runs/<run-id>/result.json` if the issue is execution-related,
or `.scout/diffs/<id>/diff.db` (zipped) if it's diff-related.

## Suggesting features

Open an issue first. scout has a deliberately narrow scope (UI-driven API
regression testing — see [README.md](README.md) for what we're *not* trying
to be). Features that broaden the scope need a strong case before
implementation.

## Development setup

scout uses [uv](https://docs.astral.sh/uv/) for environment management.

```bash
git clone https://github.com/boxprobe/scout
cd scout
uv sync --extra dev
uv run playwright install chromium
```

Run the test suite:

```bash
uv run pytest tests/ -x --tb=short
```

> **Why `uv run`?** scout pins Python ≥ 3.11 and mixes Python with a
> Rust subprocess (`hudsucker`). `uv run` guarantees the venv interpreter
> matches `pyproject.toml`'s `requires-python`; bare `python` / `pip` will
> silently use whatever system Python is first on PATH, producing
> hard-to-debug version drift.

Lint and type-check before pushing:

```bash
uv run ruff check scout/ tests/
uv run ruff format --check scout/ tests/
uv run pyright scout/
```

## Code style

- **Formatting**: `ruff format`. Line length 99.
- **Lint**: `ruff check` must pass. See `[tool.ruff.lint]` in `pyproject.toml`
  for the enabled rule sets.
- **Types**: pyright `standard` mode. All public functions should have
  annotations; private helpers may skip.
- **No bare `print`**: use `loguru`. Stray prints fail `ruff` (`T20`).
- **No bare `subprocess`**: prefer `asyncio.create_subprocess_*` or the
  helpers in `scout/collector/subprocess.py`. Sync subprocess use is
  reviewed case-by-case.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add JSONPath glob support to diff_ignore
fix(matcher): preserve query keys with comma-separated values
test: cover empty-record edge case in align()
refactor(report): extract chip rendering into helper
docs: clarify diff_ignore.json schema in README
```

Subject line in English, present tense, no trailing period, ≤ 72 chars.

## Pull requests

- One concern per PR. Bug fix + refactor + new feature should be three PRs.
- Update or add tests for any behavior change. PRs without tests get pushed
  back unless the change is purely documentation or formatting.
- If the PR changes the scenario file format, the diff report HTML format, or
  the CLI surface, flag it in the PR description — these are externally
  observable and need extra review.
- Don't add dependencies without discussing in an issue first. scout aims to
  stay light; new top-level deps need a clear case.

CI runs ruff + pyright + pytest on every PR. Required green before merge.

## Scope of changes

Keep PRs scoped to the task. Don't bundle unrelated cleanups — they make
review harder and bisecting regressions miserable. If you spot something else
worth fixing while you're in the file, open a follow-up issue or a separate
PR.

## License

By contributing, you agree your code is released under the MIT license, same
as the rest of the project (see [LICENSE](LICENSE)).
