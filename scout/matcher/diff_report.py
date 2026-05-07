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
    baseline_ver = meta.get("baseline_version", "")
    target_ver = meta.get("target_version", "")

    has_detail = any(d.get("baseline_url") for d in diffs)

    diff_rows = []
    popup_data = []  # JSON-serializable data for popup
    for idx, d in enumerate(diffs):
        status_icon = "✓" if d["status_match"] else "✗"
        status_color = "#4ade80" if d["status_match"] else "#ef4444"
        struct_icon = "✓" if d["structure_match"] else "✗"
        struct_color = "#4ade80" if d["structure_match"] else "#ef4444"
        val_match = d.get("value_match", 1)
        val_icon = "✓" if val_match else "✗"
        val_color = "#4ade80" if val_match else "#f59e0b"
        detail = d.get("diff_summary", "") or ""
        val_diff = d.get("value_diff", "") or ""

        has_diff_content = bool(detail or val_diff)
        diff_count = val_diff.count("\n") + 1 if val_diff else 0

        b_status = d.get("baseline_status", "")
        t_status = d.get("target_status", "")
        row_scenario = d.get("scenario", "")

        # Build popup data for this row
        popup_entry: dict[str, Any] = {
            "method": d["method"],
            "path": d["path"],
            "scenario": _display_scenario(row_scenario),
            "diff_summary": detail,
            "value_diff": val_diff,
        }
        if has_detail:
            popup_entry.update({
                "baseline_url": d.get("baseline_url") or "",
                "target_url": d.get("target_url") or "",
                "baseline_request": d.get("baseline_request") or "",
                "baseline_response": d.get("baseline_response") or "",
                "target_request": d.get("target_request") or "",
                "target_response": d.get("target_response") or "",
                "baseline_timestamp": d.get("baseline_timestamp") or "",
                "target_timestamp": d.get("target_timestamp") or "",
                "baseline_duration": d.get("baseline_duration"),
                "target_duration": d.get("target_duration"),
            })
        popup_data.append(popup_entry)

        # Clickable indicator in Details column
        if has_diff_content:
            detail_cell = (
                f'<td class="detail-trigger" onclick="openPopup({idx})">'
                f'<span class="diff-badge">{diff_count} diff{"s" if diff_count != 1 else ""}</span></td>'
            )
        else:
            detail_cell = '<td style="color:#555">—</td>'

        # Classify row diff types for badge filtering
        row_types = []
        if not d["status_match"]:
            row_types.append("status")
        if not d["structure_match"]:
            row_types.append("structure")
        if not val_match:
            row_types.append("value")
        data_diff_types = " ".join(row_types) if row_types else "clean"

        row = (
            f'<tr class="diff-row" data-method="{d["method"]}" data-path="{_esc(d["path"].lower())}"'
            f' data-scenario="{_esc(_display_scenario(row_scenario).lower())}" data-status="{b_status} {t_status}"'
            f' data-diff-types="{data_diff_types}">'
            f'<td style="color:#666">{idx + 1}</td>'
            f'<td class="cell-scenario">{_display_scenario(row_scenario)}</td>'
            f'<td>{d["method"]}</td>'
            f'<td>{d["path"]}</td>'
            f'<td style="color:{status_color}">{status_icon} {d.get("baseline_status", "")}'
            f'{"→" + str(d.get("target_status", "")) if not d["status_match"] else ""}</td>'
            f'<td style="color:{struct_color}">{struct_icon}</td>'
            f'<td style="color:{val_color}">{val_icon}</td>'
            f'{detail_cell}'
            f'</tr>'
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

    popup_json = _json.dumps(popup_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scout Diff — {app}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 40px; background: #0a0a0a; color: #e5e5e5; }}
  h1 {{ font-size: 22px; font-weight: 600; }}
  h2 {{ font-size: 17px; font-weight: 600; margin-top: 32px; }}
  .meta {{ display: flex; gap: 24px; margin: 16px 0; font-size: 14px; }}
  .meta span {{ padding: 4px 12px; border-radius: 6px; background: #1a1a1a; }}
  .verdict {{ font-size: 15px; font-weight: 700; color: {verdict_color}; margin: 16px 0; }}
  .summary {{ display: flex; gap: 16px; font-size: 14px; margin-bottom: 16px; }}
  .summary span {{ padding: 4px 12px; border-radius: 6px; background: #1a1a1a; }}
  .summary .badge {{ cursor: pointer; transition: outline 0.15s; }}
  .summary .badge:hover {{ outline: 1px solid #555; }}
  .summary .badge.active {{ outline: 2px solid #e5e5e5; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th {{ text-align: left; font-size: 12px; text-transform: uppercase; color: #888; padding: 10px 8px; border-bottom: 1px solid #333; }}
  td {{ padding: 10px 8px; border-bottom: 1px solid #1a1a1a; font-size: 14px; }}
  .cell-scenario {{ font-size: 13px; color: #a5b4fc; }}
  .detail-trigger {{ cursor: pointer; }}
  .detail-trigger:hover .diff-badge {{ background: #334155; }}
  .diff-badge {{ font-size: 12px; color: #f59e0b; background: #1e293b; padding: 2px 8px; border-radius: 4px; }}

  /* Popup overlay */
  .popup-overlay {{
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    z-index: 1000; justify-content: center; align-items: flex-start; padding: 40px 20px;
  }}
  .popup-overlay.open {{ display: flex; }}
  .popup {{
    background: #141414; border: 1px solid #333; border-radius: 12px;
    width: 90vw; max-width: 1200px; max-height: 85vh; overflow-y: auto;
    padding: 24px 28px; position: relative;
  }}
  .popup-close {{
    position: absolute; top: 12px; right: 16px; background: none; border: none;
    color: #888; font-size: 22px; cursor: pointer; padding: 4px 8px;
  }}
  .popup-close:hover {{ color: #e5e5e5; }}
  .popup-title {{ font-size: 15px; font-weight: 600; margin-bottom: 4px; color: #e5e5e5; }}
  .popup-subtitle {{ font-size: 13px; color: #888; margin-bottom: 16px; }}
  .popup-section {{ font-size: 12px; text-transform: uppercase; color: #888; margin: 16px 0 6px; font-weight: 600; }}
  .popup-diff {{
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; font-size: 13px; line-height: 1.6;
    background: #0a0a0a; border: 1px solid #222; border-radius: 8px;
    padding: 14px 16px; white-space: pre-wrap; word-break: break-all; color: #ccc;
    max-height: 400px; overflow: auto;
  }}
  .popup-diff .line-add {{ color: #4ade80; }}
  .popup-diff .line-rm {{ color: #ef4444; }}
  .popup-diff .line-chg {{ color: #f59e0b; }}
  .popup-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .popup-label {{ font-size: 12px; text-transform: uppercase; color: #666; margin-top: 10px; }}
  .popup-meta {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .popup-url {{ font-size: 13px; font-family: monospace; color: #a5b4fc; margin-bottom: 4px; word-break: break-all; }}
  .popup-body {{
    font-size: 12px; font-family: monospace; background: #0a0a0a; border: 1px solid #222;
    padding: 10px; border-radius: 6px; max-height: 300px; overflow: auto;
    white-space: pre-wrap; word-break: break-all; margin: 4px 0 8px 0; color: #ccc;
  }}

  .detail-label {{ font-size: 12px; text-transform: uppercase; color: #888; margin-top: 8px; }}
  .detail-meta {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .detail-url {{ font-size: 13px; font-family: monospace; color: #a5b4fc; margin-bottom: 4px; word-break: break-all; }}
  .detail-body {{ font-size: 12px; font-family: monospace; background: #111; padding: 8px; border-radius: 4px; max-height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 4px 0 8px 0; color: #ccc; }}
</style>
<script>
var POPUP_DATA = {popup_json};
document.addEventListener('DOMContentLoaded', function() {{ filterRows(''); }});
function esc(s) {{ var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}
function formatJson(s) {{
  if (!s) return '<em>empty</em>';
  try {{ return esc(JSON.stringify(JSON.parse(s), null, 2)); }}
  catch(e) {{ return esc(s.slice(0, 2000)); }}
}}
function colorDiffLine(line) {{
  if (line.startsWith('+ ')) return '<span class="line-add">' + esc(line) + '</span>';
  if (line.startsWith('- ')) return '<span class="line-rm">' + esc(line) + '</span>';
  if (line.startsWith('≠ ') || line.startsWith('~ ')) return '<span class="line-chg">' + esc(line) + '</span>';
  return esc(line);
}}
function openPopup(idx) {{
  var d = POPUP_DATA[idx];
  var el = document.getElementById('popup-overlay');
  var content = document.getElementById('popup-content');
  var html = '<div class="popup-title">' + esc(d.method) + ' ' + esc(d.path) + '</div>';
  html += '<div class="popup-subtitle">' + esc(d.scenario) + '</div>';
  if (d.diff_summary) {{
    html += '<div class="popup-section">Structure Diff</div>';
    html += '<div class="popup-diff">' + d.diff_summary.split('\\n').map(colorDiffLine).join('\\n') + '</div>';
  }}
  if (d.value_diff) {{
    html += '<div class="popup-section">Value Diff</div>';
    html += '<div class="popup-diff">' + d.value_diff.split('\\n').map(colorDiffLine).join('\\n') + '</div>';
  }}
  if (d.baseline_url !== undefined) {{
    var bDur = d.baseline_duration != null ? d.baseline_duration + 'ms' : '';
    var tDur = d.target_duration != null ? d.target_duration + 'ms' : '';
    html += '<div class="popup-section">Request / Response Detail</div>';
    html += '<div class="popup-grid">';
    html += '<div><div class="popup-label">Baseline</div>';
    html += '<div class="popup-meta">' + esc(d.baseline_timestamp) + (bDur ? '&nbsp;&nbsp;' + bDur : '') + '</div>';
    html += '<div class="popup-url">' + esc(d.baseline_url) + '</div>';
    html += '<div class="popup-label">Request</div><pre class="popup-body">' + formatJson(d.baseline_request) + '</pre>';
    html += '<div class="popup-label">Response</div><pre class="popup-body">' + formatJson(d.baseline_response) + '</pre></div>';
    html += '<div><div class="popup-label">Target</div>';
    html += '<div class="popup-meta">' + esc(d.target_timestamp) + (tDur ? '&nbsp;&nbsp;' + tDur : '') + '</div>';
    html += '<div class="popup-url">' + esc(d.target_url) + '</div>';
    html += '<div class="popup-label">Request</div><pre class="popup-body">' + formatJson(d.target_request) + '</pre>';
    html += '<div class="popup-label">Response</div><pre class="popup-body">' + formatJson(d.target_response) + '</pre></div>';
    html += '</div>';
  }}
  content.innerHTML = html;
  el.classList.add('open');
}}
function closePopup() {{
  document.getElementById('popup-overlay').classList.remove('open');
}}
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closePopup(); }});
var _activeType = 'all';
function filterByType(type) {{
  _activeType = type;
  // Update badge active state
  document.querySelectorAll('.summary .badge').forEach(function(b) {{ b.classList.remove('active'); }});
  event.target.classList.add('active');
  applyFilters();
}}
function filterRows(q) {{ applyFilters(); }}
function applyFilters() {{
  var kw = (document.getElementById('filter-input').value || '').trim();
  var field = document.getElementById('filter-field').value;
  var rows = document.querySelectorAll('.diff-row');
  var total = rows.length, visible = 0;
  rows.forEach(function(row) {{
    // Type filter
    if (_activeType !== 'all') {{
      var types = row.dataset.diffTypes || '';
      if (types.indexOf(_activeType) === -1) {{ row.style.display = 'none'; return; }}
    }}
    // Text filter
    if (kw) {{
      var match = false;
      if (field === 'method' || field === 'all') match = match || row.dataset.method === kw.toUpperCase();
      if (field === 'path' || field === 'all') match = match || row.dataset.path.indexOf(kw.toLowerCase()) !== -1;
      if (field === 'scenario' || field === 'all') match = match || row.dataset.scenario.indexOf(kw.toLowerCase()) !== -1;
      if (field === 'status' || field === 'all') match = match || row.dataset.status.indexOf(kw) !== -1;
      if (!match) {{ row.style.display = 'none'; return; }}
    }}
    row.style.display = '';
    visible++;
  }});
  var el = document.getElementById('filter-count');
  el.textContent = visible + ' / ' + total;
}}
</script>
</head>
<body>
<h1>Scout Diff — {app}</h1>
<div class="meta">
  <span>Baseline: {baseline}{' — ' + baseline_ver if baseline_ver else ''}</span>
  <span>Target: {target}{' — ' + target_ver if target_ver else ''}</span>
</div>
<div class="verdict">{verdict}</div>
<div class="summary">
  <span class="badge active" onclick="filterByType('all')">All ({summary['total_paired']})</span>
  <span class="badge" style="color:#ef4444" onclick="filterByType('status')">{summary['status_mismatches']} status</span>
  <span class="badge" style="color:#ef4444" onclick="filterByType('structure')">{summary['structure_mismatches']} structure</span>
  <span class="badge" style="color:#f59e0b" onclick="filterByType('value')">{value_changes} value</span>
  <span class="badge" style="color:#facc15" onclick="filterByType('endpoint')">{summary['missing_endpoints']} endpoint</span>
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

<div id="popup-overlay" class="popup-overlay" onclick="if(event.target===this)closePopup()">
  <div class="popup">
    <button class="popup-close" onclick="closePopup()">✕</button>
    <div id="popup-content"></div>
  </div>
</div>

</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
