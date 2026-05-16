# scout

**UI-driven API regression testing.** Maintained by [BoxProbe](https://boxprobe.com).

scout drives your web app's UI like a real user, records the resulting API
traffic, and produces a diff report between two runs. When a deploy
silently changes a response shape, scout tells you which endpoint changed,
in which user flow, and exactly how.

Scenarios are recorded once and replay deterministically — no AI in the
hot path, no per-request API fees, no SaaS subscription. Same scenario on
the same app produces the same trace, at **$0 per run**.

---

## Three pillars

| Property | How |
|---|---|
| **Deterministic** | Pixel-anchored Locators make element resolution pure math, not a probabilistic selector match. No LLM runs in the hot path. Same input, same trace. |
| **Near-zero cost** | No tokens consumed, no per-request API fees. Cheap enough to run on every PR or nightly without anyone asking about cost. |
| **Auditable** | Open source, no telemetry, no upload step — everything stays on the machine running scout. Read the Python before letting it into your CI. |

---

## Where to start

- [Quickstart](quickstart.md) — install scout, write a scenario, see your
  first diff report
- [Scenarios](scenarios.md) — the `Scenario`, `Locator`, and `Page` APIs
- [Diff ignore rules](diff-ignore.md) — how to suppress timestamp / ID
  noise without losing real regressions
- [CLI reference](cli.md) — every subcommand and its options

---

## Try it on a real app

[**github.com/boxprobe/scout-medusa**](https://github.com/boxprobe/scout-medusa)
is a fully reproducible demo: two pinned versions of
[Medusa](https://github.com/medusajs/medusa) running side by side, 15
admin scenarios, one HTML diff report. Clone, `docker compose up`, run
scout twice, see the diff.

---

## Status

scout is **alpha** (`0.1.x`). The CLI surface and scenario DSL are still
stabilizing; expect breaking changes between minor versions until `1.0`.
See the [changelog](changelog.md) for what's shipped.
