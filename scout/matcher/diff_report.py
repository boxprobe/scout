"""Diff HTML report — visual comparison of two API recordings.

Generates a self-contained HTML file with:
- Endpoint comparison table (sortable, filterable)
- Popup with structure/value diff details
- Interactive diff_ignore editor (status_only toggle, field/path ignore)
- Download button to export diff_ignore.json
"""

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
    *,
    diff_ignore: dict[str, Any] | None = None,
) -> None:
    """Write a self-contained HTML diff report with interactive editing."""
    app = meta.get("app", "")
    baseline = meta.get("baseline_run_id", "")
    target = meta.get("target_run_id", "")
    baseline_ver = meta.get("baseline_version", "")
    target_ver = meta.get("target_version", "")

    has_detail = any(d.get("baseline_url") for d in diffs)
    di_json = _json.dumps(diff_ignore or {}, ensure_ascii=False)

    diff_rows = []
    popup_data = []
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
        step_seq = d.get("step_seq")
        step_label = d.get("step_label") or ""
        step_display = f"{step_seq}: {step_label}" if step_seq else ""
        b_offset = d.get("baseline_offset_ms")
        t_offset = d.get("target_offset_ms")
        if b_offset is not None and t_offset is not None:
            timing_display = f"{b_offset} / {t_offset}"
        elif b_offset is not None:
            timing_display = f"{b_offset} / —"
        elif t_offset is not None:
            timing_display = f"— / {t_offset}"
        else:
            timing_display = ""

        popup_entry: dict[str, Any] = {
            "method": d["method"],
            "path": d["path"],
            "scenario": row_scenario,
            "step_seq": step_seq,
            "step_label": step_label,
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

        if has_diff_content:
            detail_cell = (
                f'<td class="detail-trigger" onclick="openPopup({idx})">'
                f'<span class="diff-badge">{diff_count} diff{"s" if diff_count != 1 else ""}</span></td>'
            )
        else:
            detail_cell = '<td style="color:#555">—</td>'

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
            f' data-step="{_esc(step_display.lower())}"'
            f' data-raw-scenario="{_esc(row_scenario)}" data-raw-path="{_esc(d["path"])}"'
            f' data-step-seq="{step_seq if step_seq is not None else ""}"'
            f' data-diff-types="{data_diff_types}">'
            f'<td style="color:#666">{idx + 1}</td>'
            f'<td class="cell-scenario">{_display_scenario(row_scenario)}</td>'
            f'<td class="cell-step">{_esc(step_display)}</td>'
            f'<td class="cell-timing">{timing_display}</td>'
            f'<td>{d["method"]}</td>'
            f'<td>{d["path"]}</td>'
            f'<td style="color:{status_color}">{status_icon} {d.get("baseline_status", "")}'
            f'{"→" + str(d.get("target_status", "")) if not d["status_match"] else ""}</td>'
            f'<td style="color:{struct_color}">{struct_icon}</td>'
            f'<td style="color:{val_color}">{val_icon}</td>'
            f'{detail_cell}'
            f'<td class="actions-cell">'
            f'<button class="so-btn" data-path="{_esc(d["path"])}" data-scenario="{_esc(row_scenario or "*")}"'
            f' data-step-seq="{step_seq if step_seq is not None else "*"}"'
            f' onclick="toggleSO(this)" title="Toggle status_only">SO</button>'
            f'</td>'
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
  .summary {{ display: flex; gap: 16px; font-size: 14px; margin-bottom: 16px; flex-wrap: wrap; }}
  .summary span {{ padding: 4px 12px; border-radius: 6px; background: #1a1a1a; }}
  .summary .badge {{ cursor: pointer; transition: outline 0.15s; }}
  .summary .badge:hover {{ outline: 1px solid #555; }}
  .summary .badge.active {{ outline: 2px solid #e5e5e5; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th {{ text-align: left; font-size: 12px; text-transform: uppercase; color: #888; padding: 10px 8px; border-bottom: 1px solid #333; }}
  td {{ padding: 10px 8px; border-bottom: 1px solid #1a1a1a; font-size: 14px; }}
  .cell-scenario {{ font-size: 13px; color: #a5b4fc; }}
  .cell-step {{ font-size: 12px; color: #94a3b8; white-space: nowrap; }}
  .cell-timing {{ font-size: 11px; color: #64748b; white-space: nowrap; font-family: 'SF Mono', monospace; }}
  .detail-trigger {{ cursor: pointer; }}
  .detail-trigger:hover .diff-badge {{ background: #334155; }}
  .diff-badge {{ font-size: 12px; color: #f59e0b; background: #1e293b; padding: 2px 8px; border-radius: 4px; }}

  /* SO button */
  .actions-cell {{ white-space: nowrap; }}
  .so-btn {{
    padding: 3px 8px; font-size: 11px; font-weight: 700; border-radius: 4px; cursor: pointer;
    border: 1px solid #444; background: #1a1a1a; color: #888; transition: all 0.15s;
  }}
  .so-btn:hover {{ color: #e5e5e5; border-color: #888; }}
  .so-btn.is-active {{ background: #0d9488; color: #fff; border-color: #0d9488; }}

  /* Field/path ignore buttons in popup */
  .field-btn {{
    display: inline-block; padding: 2px 8px; margin: 2px; font-size: 11px;
    font-family: 'SF Mono', monospace; border-radius: 4px; cursor: pointer;
    border: 1px solid #444; background: #1a1a1a; color: #888; transition: all 0.15s;
  }}
  .field-btn:hover {{ color: #e5e5e5; border-color: #888; }}
  .field-btn.is-ignored {{ background: #0d9488; color: #fff; border-color: #0d9488; }}

  /* Config panel */
  .config-panel {{
    margin: 16px 0; background: #111; border: 1px solid #333; border-radius: 8px; padding: 16px;
  }}
  .config-panel summary {{ font-size: 13px; font-weight: 600; color: #888; cursor: pointer; }}
  .config-editor {{
    font-family: 'SF Mono', monospace; font-size: 12px; line-height: 1.5;
    background: #0a0a0a; border: 1px solid #222; border-radius: 6px; padding: 12px;
    margin-top: 8px; width: 100%; min-height: 200px; max-height: 500px; resize: vertical;
    color: #ccc; tab-size: 2; outline: none;
  }}
  .config-editor:focus {{ border-color: #555; }}
  .config-error {{ font-size: 12px; color: #ef4444; margin-top: 4px; }}
  .download-btn {{
    display: inline-block; margin-top: 8px; padding: 6px 16px; font-size: 13px; font-weight: 600;
    background: #0d9488; color: #fff; border: none; border-radius: 6px; cursor: pointer;
  }}
  .download-btn:hover {{ background: #0f766e; }}

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
  .toast {{
    position: fixed; top: 16px; right: 24px; z-index: 2000;
    padding: 10px 20px; border-radius: 8px; font-size: 13px; font-weight: 600;
    color: #10b981; background: #1a1a1a; border: 1px solid rgba(16,185,129,.3);
    box-shadow: 0 4px 12px rgba(0,0,0,.3);
    animation: toast-in 0.2s ease, toast-out 0.3s ease 2s forwards;
  }}
  @keyframes toast-in {{ from {{ opacity: 0; transform: translateY(-8px); }} to {{ opacity: 1; }} }}
  @keyframes toast-out {{ to {{ opacity: 0; transform: translateY(-8px); }} }}
  .changed-marker {{ color: #f59e0b; font-size: 11px; margin-left: 8px; }}
</style>
<script>
var POPUP_DATA = {popup_json};
var DI = {di_json};  // Current diff_ignore config
var DI_CHANGED = false;

// -- diff_ignore helpers --

function diFields() {{ return DI.fields || []; }}
function diStatusOnly() {{ return DI.status_only || []; }}

function diHasField(name) {{ return diFields().indexOf(name) !== -1; }}

function diHasStatusOnly(path, scenario, stepSeq) {{
  return diStatusOnly().some(function(r) {{
    return r.path === path && (r.scenario || '*') === scenario && String(r.step_seq || '*') === String(stepSeq);
  }});
}}

function diAddField(name) {{
  if (!DI.fields) DI.fields = [];
  if (DI.fields.indexOf(name) === -1) DI.fields.push(name);
  diOnChange();
}}

function diRemoveField(name) {{
  if (!DI.fields) return;
  DI.fields = DI.fields.filter(function(f) {{ return f !== name; }});
  diOnChange();
}}

function diAddStatusOnly(path, scenario, stepSeq) {{
  if (!DI.status_only) DI.status_only = [];
  if (!diHasStatusOnly(path, scenario, stepSeq)) {{
    DI.status_only.push({{ path: path, scenario: scenario, step_seq: stepSeq }});
  }}
  diOnChange();
}}

function diRemoveStatusOnly(path, scenario, stepSeq) {{
  if (!DI.status_only) return;
  DI.status_only = DI.status_only.filter(function(r) {{
    return !(r.path === path && (r.scenario || '*') === scenario && String(r.step_seq || '*') === String(stepSeq));
  }});
  diOnChange();
}}

function diOnChange() {{
  DI_CHANGED = true;
  document.getElementById('config-json').value = JSON.stringify(DI, null, 2);
  document.getElementById('config-error').textContent = '';
  var marker = document.getElementById('changed-marker');
  if (marker) {{ marker.style.display = 'inline'; marker.closest('details').open = true; }}
}}

// Sync manual textarea edits back to DI
document.addEventListener('DOMContentLoaded', function() {{
  var editor = document.getElementById('config-json');
  editor.addEventListener('input', function() {{
    var errEl = document.getElementById('config-error');
    try {{
      var parsed = JSON.parse(editor.value);
      DI = parsed;
      DI_CHANGED = true;
      errEl.textContent = '';
      var marker = document.getElementById('changed-marker');
      if (marker) marker.style.display = 'inline';
    }} catch(e) {{
      errEl.textContent = 'Invalid JSON: ' + e.message;
    }}
  }});
}});

var IS_SERVED = location.protocol !== 'file:';

function saveDI() {{
  var btn = document.querySelector('#config-buttons .download-btn');
  if (btn) {{ btn.disabled = true; btn.textContent = 'Saving\u2026'; }}
  fetch('/api/save', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(DI, null, 2)
  }}).then(function(r) {{
    if (r.ok) {{
      DI_CHANGED = false;
      var marker = document.getElementById('changed-marker');
      if (marker) marker.style.display = 'none';
      if (btn) {{
        btn.textContent = '\u2713 Saved';
        btn.style.background = '#065f46'; btn.style.color = '#6ee7b7';
        setTimeout(function() {{
          btn.textContent = 'Save to repo';
          btn.style.background = ''; btn.style.color = '';
          btn.disabled = false;
        }}, 2000);
      }}
    }} else {{
      r.json().then(function(d) {{
        if (btn) {{
          btn.textContent = '\u2717 ' + (d.error || 'save failed');
          btn.style.background = '#7f1d1d'; btn.style.color = '#fca5a5';
          setTimeout(function() {{
            btn.textContent = 'Save to repo';
            btn.style.background = ''; btn.style.color = '';
            btn.disabled = false;
          }}, 3000);
        }}
      }});
    }}
  }}).catch(function(e) {{
    if (btn) {{
      btn.textContent = '\u2717 ' + e.message;
      btn.style.background = '#7f1d1d'; btn.style.color = '#fca5a5';
      setTimeout(function() {{
        btn.textContent = 'Save to repo';
        btn.style.background = ''; btn.style.color = '';
        btn.disabled = false;
      }}, 3000);
    }}
  }});
}}

function downloadDI() {{
  var blob = new Blob([JSON.stringify(DI, null, 2) + '\\n'], {{ type: 'application/json' }});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'diff_ignore.json';
  a.click();
  URL.revokeObjectURL(a.href);
  showToast('Downloaded diff_ignore.json');
}}

function showToast(msg) {{
  var existing = document.querySelector('.toast');
  if (existing) existing.remove();
  var t = document.createElement('div');
  t.className = 'toast';
  t.textContent = '\\u2713 ' + msg;
  document.body.appendChild(t);
  setTimeout(function() {{ t.remove(); }}, 2500);
}}

// -- SO button --

function toggleSO(btn) {{
  var path = btn.dataset.path;
  var scenario = btn.dataset.scenario;
  var stepSeq = btn.dataset.stepSeq;
  if (btn.classList.contains('is-active')) {{
    diRemoveStatusOnly(path, scenario, stepSeq);
    btn.classList.remove('is-active');
    btn.title = 'Add to status_only';
  }} else {{
    diAddStatusOnly(path, scenario, stepSeq);
    btn.classList.add('is-active');
    btn.title = 'Remove from status_only';
  }}
}}

// -- Field/path ignore --

function toggleField(btn, name) {{
  if (btn.classList.contains('is-ignored')) {{
    diRemoveField(name);
    btn.classList.remove('is-ignored');
    // Update all buttons for same field
    document.querySelectorAll('.field-btn[data-field="' + name + '"]').forEach(function(b) {{ b.classList.remove('is-ignored'); }});
  }} else {{
    diAddField(name);
    btn.classList.add('is-ignored');
    document.querySelectorAll('.field-btn[data-field="' + name + '"]').forEach(function(b) {{ b.classList.add('is-ignored'); }});
  }}
}}

// -- Init SO button states --
function initSOButtons() {{
  document.querySelectorAll('.so-btn').forEach(function(btn) {{
    if (diHasStatusOnly(btn.dataset.path, btn.dataset.scenario, btn.dataset.stepSeq)) {{
      btn.classList.add('is-active');
      btn.title = 'Remove from status_only';
    }}
  }});
}}

// -- Filtering --
document.addEventListener('DOMContentLoaded', function() {{ filterRows(''); initSOButtons(); }});
function esc(s) {{ var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}
function formatJson(s) {{
  if (!s) return '<em>empty</em>';
  try {{ return esc(JSON.stringify(JSON.parse(s), null, 2)); }}
  catch(e) {{ return esc(s.slice(0, 2000)); }}
}}
function colorDiffLine(line) {{
  if (line.startsWith('+ ')) return '<span class="line-add">' + esc(line) + '</span>';
  if (line.startsWith('- ')) return '<span class="line-rm">' + esc(line) + '</span>';
  if (line.startsWith('\\u2260 ') || line.startsWith('~ ')) return '<span class="line-chg">' + esc(line) + '</span>';
  return esc(line);
}}

// Extract field names and paths from diff text
function extractIgnorables(text) {{
  if (!text) return [];
  var items = {{}};
  var re = /^[\\u2260+\\-~]\\s+(\\$\\S+?):/gm;
  var m;
  while ((m = re.exec(text)) !== null) {{
    var fullPath = m[1];
    items[fullPath] = true;
    // Also extract the leaf field name
    var dot = fullPath.lastIndexOf('.');
    if (dot !== -1) {{
      var leaf = fullPath.substring(dot + 1);
      if (leaf && !leaf.match(/^\\[/)) items[leaf] = true;
    }}
  }}
  return Object.keys(items);
}}

function openPopup(idx) {{
  var d = POPUP_DATA[idx];
  var el = document.getElementById('popup-overlay');
  var content = document.getElementById('popup-content');
  var stepDisplay = d.step_seq ? d.step_seq + ': ' + (d.step_label || '') : '';
  var html = '<div class="popup-title">' + esc(d.method) + ' ' + esc(d.path) + '</div>';
  html += '<div class="popup-subtitle">' + esc((d.scenario || '').replace(/\\//g, '.')) + (stepDisplay ? ' \\u2014 step ' + esc(stepDisplay) : '') + '</div>';
  if (d.diff_summary) {{
    html += '<div class="popup-section">Structure Diff</div>';
    html += '<div class="popup-diff">' + d.diff_summary.split('\\n').map(colorDiffLine).join('\\n') + '</div>';
  }}
  if (d.value_diff) {{
    html += '<div class="popup-section">Value Diff</div>';
    html += '<div class="popup-diff">' + d.value_diff.split('\\n').map(colorDiffLine).join('\\n') + '</div>';
  }}
  // Ignorable fields/paths buttons
  var ignorables = extractIgnorables((d.diff_summary || '') + '\\n' + (d.value_diff || ''));
  if (ignorables.length > 0) {{
    html += '<div class="popup-section">Ignore Fields / Paths</div><div>';
    ignorables.forEach(function(name) {{
      var cls = diHasField(name) ? 'field-btn is-ignored' : 'field-btn';
      html += '<button class="' + cls + '" data-field="' + esc(name) + '" onclick="toggleField(this, \\'' + esc(name).replace(/'/g, "\\\\'") + '\\')">' + esc(name) + '</button>';
    }});
    html += '</div>';
  }}
  // Detail panels
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
    if (_activeType !== 'all') {{
      var types = row.dataset.diffTypes || '';
      if (types.indexOf(_activeType) === -1) {{ row.style.display = 'none'; return; }}
    }}
    if (kw) {{
      var match = false;
      if (field === 'method' || field === 'all') match = match || row.dataset.method === kw.toUpperCase();
      if (field === 'path' || field === 'all') match = match || row.dataset.path.indexOf(kw.toLowerCase()) !== -1;
      if (field === 'scenario' || field === 'all') match = match || row.dataset.scenario.indexOf(kw.toLowerCase()) !== -1;
      if (field === 'step' || field === 'all') match = match || (row.dataset.step || '').indexOf(kw.toLowerCase()) !== -1;
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

<!-- diff_ignore config panel -->
<details class="config-panel">
  <summary>diff_ignore.json <span id="changed-marker" class="changed-marker" style="display:none">● modified</span></summary>
  <textarea id="config-json" class="config-editor" spellcheck="false">{_esc(_json.dumps(diff_ignore or {}, indent=2, ensure_ascii=False))}</textarea>
  <div id="config-error" class="config-error"></div>
  <div id="config-buttons" style="margin-top:8px;display:flex;gap:8px;"></div>
  <script>
  (function() {{
    var btns = document.getElementById('config-buttons');
    if (IS_SERVED) {{
      btns.innerHTML = '<button class="download-btn" onclick="saveDI()">Save to repo</button>'
        + '<button class="download-btn" style="background:#333;" onclick="downloadDI()">Download</button>';
    }} else {{
      btns.innerHTML = '<button class="download-btn" onclick="downloadDI()">Download diff_ignore.json</button>';
    }}
  }})();
  </script>
</details>

<h2>Endpoint Comparison</h2>
<div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;">
  <select id="filter-field" onchange="filterRows(document.getElementById('filter-input').value)"
    style="padding:6px 8px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e5e5e5;font-size:13px;">
    <option value="all">All</option>
    <option value="method">Method</option>
    <option value="path">Path</option>
    <option value="scenario">Scenario</option>
    <option value="step">Step</option>
    <option value="status">Status</option>
  </select>
  <input id="filter-input" type="text" placeholder="Filter…" oninput="filterRows(this.value)"
    style="width:260px;padding:6px 10px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e5e5e5;font-size:13px;outline:none;">
  <span id="filter-count" style="font-size:12px;color:#888;"></span>
</div>
<table>
<thead><tr><th>#</th><th>Scenario</th><th>Step</th><th>ms</th><th>Method</th><th>Path</th><th>Status</th><th>Structure</th><th>Value</th><th>Details</th><th></th></tr></thead>
<tbody>
{"".join(diff_rows) if diff_rows else '<tr><td colspan="11" style="color:#888">No paired endpoints</td></tr>'}
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
