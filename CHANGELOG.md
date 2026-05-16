# Changelog

All notable changes to scout are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches `1.0.0`. While in `0.x`, breaking changes may occur between
minor versions; patch versions remain backward-compatible bug fixes.

## [Unreleased]

## [0.1.3] - 2026-05-16

Initial public release on PyPI. Prior `0.1.x` versions were distributed
internally via a private package registry; this is the first cut intended
for external consumers.

### Features at this version

- `scout run` — execute pre-recorded Python scenarios via Playwright,
  capture API traffic through a recording proxy
- `scout verify` — debug-mode scenario execution with screenshots, no proxy
- `scout diff` — compare two runs' API recordings, produce HTML diff report
  with structural, value, and known-change classification
- `scout runs` — list local run history
- Pixel-anchored `Locator` API with `abs` / `rel` / `dxy` positioning
- `diff_ignore.json` rule format for field, value-type, endpoint, and
  status-only noise suppression
- HTML diff report with filterable endpoint table, popup body diffs, and
  known-change badges
- JUnit XML report alongside HTML for CI integration

[Unreleased]: https://github.com/boxprobe/scout/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/boxprobe/scout/releases/tag/v0.1.3
