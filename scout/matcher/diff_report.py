"""Diff HTML report — visual comparison of two API recordings."""

from __future__ import annotations

from pathlib import Path
from typing import Any


import html as _html
import json as _json


def _esc(s: str) -> str:
    return _html.escape(s)


def _display_scenario(s: str) -> str:
    """Convert scenario path to display format: auth/login-success → auth.login-success."""
    return s.replace("/", ".")


def _format_body(body: str | None) -> str:
    if not body:
        return "<em>empty</em>"
    try:
        obj = _json.loads(body)
        return _esc(_json.dumps(obj, indent=2, ensure_ascii=False))
    except Exception:
        return _esc(body[:2000])


def generate_diff_html(
    meta: dict[str, str],
    diffs: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    summary: dict[str, int],
    output_path: Path,
) -> None:
    """Write a self-contained HTML diff report."""
    app = meta.get("app", "")
    baseline = meta.get("baseline_run_id", "")
    target = meta.get("target_run_id", "")

    has_detail = any(d.get("baseline_url") for d in diffs)

    diff_rows = []
    for idx, d in enumerate(diffs):
        status_icon = "✓" if d["status_match"] else "✗"
        status_color = "#4ade80" if d["status_match"] else "#ef4444"
        struct_icon = "✓" if d["structure_match"] else "✗"
        struct_color = "#4ade80" if d["structure_match"] else "#ef4444"
        val_match = d.get("value_match", 1)
        val_icon = "✓" if val_match else "✗"
        val_color = "#4ade80" if val_match else "#f59e0b"
        detail = d.get("diff_summary", "") or ""
        detail_html = detail.replace("\n", "<br>").replace(" ", "&nbsp;") if detail else ""
        val_diff = d.get("value_diff", "") or ""
        val_diff_html = _esc(val_diff).replace("\n", "<br>").replace(" ", "&nbsp;") if val_diff else ""

        b_status = d.get("baseline_status", "")
        t_status = d.get("target_status", "")
        row_scenario = d.get("scenario", "")
        row = (
            f'<tr class="diff-row" data-method="{d["method"]}" data-path="{_esc(d["path"].lower())}"'
            f' data-scenario="{_esc(_display_scenario(row_scenario).lower())}" data-status="{b_status} {t_status}">'
            f'<td style="color:#666">{idx + 1}</td>'
            f'<td style="font-size:12px;color:#a5b4fc;">{_display_scenario(row_scenario)}</td>'
            f'<td>{d["method"]}</td>'
            f'<td>{d["path"]}</td>'
            f'<td style="color:{status_color}">{status_icon} {d.get("baseline_status", "")}'
            f'{"→" + str(d.get("target_status", "")) if not d["status_match"] else ""}</td>'
            f'<td style="color:{struct_color}">{struct_icon}</td>'
            f'<td style="color:{val_color}">{val_icon}</td>'
            f'<td style="font-size:11px;font-family:monospace;color:#888">'
        )
        if has_detail:
            row += f"<span onclick=\"toggle('detail-{idx}')\" style=\"cursor:pointer;color:#888;font-size:16px;\">⋯</span>"
        row += (
            f'{detail_html}'
            f'{"<br>" if detail_html and val_diff_html else ""}{val_diff_html}</td>'
        )
        row += '</tr>'

        if has_detail:
            b_url = _esc(d.get("baseline_url") or "")
            t_url = _esc(d.get("target_url") or "")
            b_req = _format_body(d.get("baseline_request"))
            b_resp = _format_body(d.get("baseline_response"))
            t_req = _format_body(d.get("target_request"))
            t_resp = _format_body(d.get("target_response"))
            b_ts = _esc(d.get("baseline_timestamp") or "")
            t_ts = _esc(d.get("target_timestamp") or "")
            b_dur = d.get("baseline_duration")
            t_dur = d.get("target_duration")
            b_dur_str = f"{b_dur}ms" if b_dur is not None else ""
            t_dur_str = f"{t_dur}ms" if t_dur is not None else ""
            row += (
                f'<tr id="detail-{idx}" style="display:none">'
                f'<td colspan="8" style="padding:12px 8px">'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">'
                f'<div><div class="detail-label">Baseline</div>'
                f'<div class="detail-meta">{b_ts}{"&nbsp;&nbsp;" + b_dur_str if b_dur_str else ""}</div>'
                f'<div class="detail-url">{b_url}</div>'
                f'<div class="detail-label">Request</div><pre class="detail-body">{b_req}</pre>'
                f'<div class="detail-label">Response</div><pre class="detail-body">{b_resp}</pre></div>'
                f'<div><div class="detail-label">Target</div>'
                f'<div class="detail-meta">{t_ts}{"&nbsp;&nbsp;" + t_dur_str if t_dur_str else ""}</div>'
                f'<div class="detail-url">{t_url}</div>'
                f'<div class="detail-label">Request</div><pre class="detail-body">{t_req}</pre>'
                f'<div class="detail-label">Response</div><pre class="detail-body">{t_resp}</pre></div>'
                f'</div></td></tr>'
            )

        diff_rows.append(row)

    missing_rows = []
    for mi, m in enumerate(missing):
        side_label = "Added" if m["side"] == "target" else "Removed"
        side_color = "#facc15" if m["side"] == "target" else "#ef4444"
        missing_rows.append(
            f'<tr>'
            f'<td style="color:#666">{mi + 1}</td>'
            f'<td style="font-size:12px;color:#a5b4fc;">{_display_scenario(m.get("scenario", ""))}</td>'
            f'<td style="color:{side_color}">{side_label}</td>'
            f'<td>{m["method"]}</td>'
            f'<td>{m["path"]}</td>'
            f'<td>{m.get("status_code", "")}</td>'
            f'</tr>'
        )

    has_issues = summary["status_mismatches"] + summary["structure_mismatches"] + summary["missing_endpoints"] > 0
    value_changes = summary.get("value_mismatches", 0)
    verdict_color = "#ef4444" if has_issues else "#4ade80"
    verdict = "REGRESSION DETECTED" if has_issues else "NO REGRESSION"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scout Diff — {app}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 40px; background: #0a0a0a; color: #e5e5e5; }}
  h1 {{ font-size: 20px; font-weight: 600; }}
  h2 {{ font-size: 16px; font-weight: 600; margin-top: 32px; }}
  .meta {{ display: flex; gap: 24px; margin: 16px 0; font-size: 13px; }}
  .meta span {{ padding: 4px 12px; border-radius: 6px; background: #1a1a1a; }}
  .verdict {{ font-size: 14px; font-weight: 700; color: {verdict_color}; margin: 16px 0; }}
  .summary {{ display: flex; gap: 16px; font-size: 13px; margin-bottom: 16px; }}
  .summary span {{ padding: 4px 12px; border-radius: 6px; background: #1a1a1a; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th {{ text-align: left; font-size: 11px; text-transform: uppercase; color: #888; padding: 8px; border-bottom: 1px solid #333; }}
  td {{ padding: 8px; border-bottom: 1px solid #1a1a1a; font-size: 13px; }}
  button {{ background: #333; border: none; color: #e5e5e5; cursor: pointer; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
  button:hover {{ background: #555; }}
  .detail-label {{ font-size: 11px; text-transform: uppercase; color: #888; margin-top: 8px; }}
  .detail-meta {{ font-size: 11px; color: #888; margin-bottom: 4px; }}
  .detail-url {{ font-size: 12px; font-family: monospace; color: #a5b4fc; margin-bottom: 4px; word-break: break-all; }}
  .detail-body {{ font-size: 11px; font-family: monospace; background: #111; padding: 8px; border-radius: 4px; max-height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 4px 0 8px 0; color: #ccc; }}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {{ filterRows(''); }});
function toggle(id) {{
  var el = document.getElementById(id);
  el.style.display = el.style.display === 'none' ? 'table-row' : 'none';
}}
function filterRows(q) {{
  var kw = q.trim();
  var field = document.getElementById('filter-field').value;
  var rows = document.querySelectorAll('.diff-row');
  var total = rows.length, visible = 0;
  rows.forEach(function(row) {{
    if (!kw) {{ row.style.display = ''; visible++; return; }}
    var match = false;
    if (field === 'method' || field === 'all') match = match || row.dataset.method === kw.toUpperCase();
    if (field === 'path' || field === 'all') match = match || row.dataset.path.indexOf(kw.toLowerCase()) !== -1;
    if (field === 'scenario' || field === 'all') match = match || row.dataset.scenario.indexOf(kw.toLowerCase()) !== -1;
    if (field === 'status' || field === 'all') match = match || row.dataset.status.indexOf(kw) !== -1;
    row.style.display = match ? '' : 'none';
    if (match) visible++;
    var detail = row.nextElementSibling;
    if (detail && detail.id && detail.id.startsWith('detail-')) {{
      if (!match) detail.style.display = 'none';
    }}
  }});
  var el = document.getElementById('filter-count');
  el.textContent = kw ? visible + ' / ' + total : total + ' rows';
}}
</script>
</head>
<body>
<h1>Scout Diff — {app}</h1>
<div class="meta">
  <span>Baseline: {baseline}</span>
  <span>Target: {target}</span>
</div>
<div class="verdict">{verdict}</div>
<div class="summary">
  <span>{summary['total_paired']} paired</span>
  <span style="color:#ef4444">{summary['status_mismatches']} status changes</span>
  <span style="color:#ef4444">{summary['structure_mismatches']} structure changes</span>
  <span style="color:#f59e0b">{value_changes} value changes</span>
  <span style="color:#facc15">{summary['missing_endpoints']} endpoint changes</span>
</div>
<div class="summary">
  <span>Baseline: {summary.get('baseline_4xx', 0)} 4xx, {summary.get('baseline_5xx', 0)} 5xx</span>
  <span>Target: {summary.get('target_4xx', 0)} 4xx, {summary.get('target_5xx', 0)} 5xx</span>
</div>

<h2>Endpoint Comparison</h2>
<div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;">
  <select id="filter-field" onchange="filterRows(document.getElementById('filter-input').value)"
    style="padding:6px 8px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e5e5e5;font-size:13px;">
    <option value="all">All</option>
    <option value="method">Method</option>
    <option value="path">Path</option>
    <option value="scenario">Scenario</option>
    <option value="status">Status</option>
  </select>
  <input id="filter-input" type="text" placeholder="Filter…" oninput="filterRows(this.value)"
    style="width:260px;padding:6px 10px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e5e5e5;font-size:13px;outline:none;">
  <span id="filter-count" style="font-size:12px;color:#888;"></span>
</div>
<table>
<thead><tr><th>#</th><th>Scenario</th><th>Method</th><th>Path</th><th>Status</th><th>Structure</th><th>Value</th><th>Details</th></tr></thead>
<tbody>
{"".join(diff_rows) if diff_rows else '<tr><td colspan="8" style="color:#888">No paired endpoints</td></tr>'}
</tbody>
</table>

{"<h2>Endpoint Changes</h2>" + chr(10) + '<table>' + chr(10) + '<thead><tr><th>#</th><th>Scenario</th><th>Change</th><th>Method</th><th>Path</th><th>Status</th></tr></thead>' + chr(10) + '<tbody>' + chr(10) + "".join(missing_rows) + chr(10) + '</tbody>' + chr(10) + '</table>' if missing_rows else ""}

</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
