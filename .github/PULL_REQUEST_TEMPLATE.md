<!--
Thanks for the PR! A few quick checks before submitting:
-->

## What this changes

<!-- One-paragraph summary of the change and its motivation. -->

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Docs / formatting
- [ ] Test only

## Checklist

- [ ] Linked issue (or this is a trivial doc/typo PR)
- [ ] Tests added or updated for behavior changes
- [ ] `uv run pytest tests/ -x --tb=short -m "not e2e"` passes locally
- [ ] `uv run ruff check scout/ tests/` passes
- [ ] `uv run pyright scout/` passes
- [ ] Externally-observable surfaces flagged (scenario file format, diff report HTML, CLI flags)

## Notes for reviewers

<!-- Anything reviewers should know: tricky parts, why a specific approach
was chosen, follow-ups deliberately deferred. -->
