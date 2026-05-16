"""HTML report generation — self-contained single-file report."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scout.runner.executor import ExecutionResult


def generate_html(
    results: dict[str, ExecutionResult],
    output_path: Path,
    *,
    run_id: str = "",
    app_name: str = "",
    wall_ms: int | None = None,
) -> None:
    passed = sum(1 for r in results.values() if r.success)
    failed = len(results) - passed
    total_ms = wall_ms if wall_ms is not None else sum(r.duration_ms for r in results.values())
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    rows = []
    for idx, (path, result) in enumerate(results.items(), 1):
        status = "PASSED" if result.success else "FAILED"
        color = "#4ade80" if result.success else "#ef4444"
        errors = "<br>".join(result.errors) if result.errors else ""
        display_name = path.replace("/", ".")
        duration = f"{result.duration_ms:,}ms"
        rows.append(
            f'<tr><td style="color:#666">{idx}</td>'
            f"<td>{display_name}</td>"
            f'<td style="color:{color};font-weight:600">{status}</td>'
            f"<td>{duration}</td>"
            f'<td style="font-size:12px;color:#888">{errors}</td></tr>'
        )

    table_rows = "\n".join(rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scout Report — {app_name or run_id}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 40px; background: #0a0a0a; color: #e5e5e5; }}
  h1 {{ font-size: 20px; font-weight: 600; }}
  .summary {{ display: flex; gap: 24px; margin: 16px 0; font-size: 14px; }}
  .summary span {{ padding: 4px 12px; border-radius: 6px; background: #1a1a1a; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th {{ text-align: left; font-size: 11px; text-transform: uppercase; color: #888; padding: 8px; border-bottom: 1px solid #333; }}
  td {{ padding: 8px; border-bottom: 1px solid #1a1a1a; font-size: 13px; }}
</style>
</head>
<body>
<h1>Scout Report{" — " + app_name if app_name else ""}</h1>
<div class="summary">
  <span>Run: {run_id}</span>
  <span style="color:#4ade80">{passed} passed</span>
  <span style="color:#ef4444">{failed} failed</span>
  <span>{total_ms:,}ms</span>
  <span>{timestamp}</span>
</div>
<table>
<thead><tr><th>#</th><th>Scenario</th><th>Status</th><th>Duration</th><th>Errors</th></tr></thead>
<tbody>
{table_rows}
</tbody>
</table>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
