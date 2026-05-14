"""Diff HTML report — visual comparison of two API recordings.

Generates a self-contained HTML file with:
- Endpoint comparison table (sortable, filterable)
- Popup with structure/value diff details
- Interactive diff_ignore editor (status_only toggle, field/path ignore)
- Download button to export diff_ignore.json (user-chosen filename)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scout.matcher.noise import DiffIgnoreConfig, load_diff_ignore


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
    repo_root: Path | None = None,
) -> None:
    """Write a self-contained HTML diff report with interactive editing."""
    app = meta.get("app", "")
    baseline = meta.get("baseline_run_id", "")
    target = meta.get("target_run_id", "")
    baseline_ver = meta.get("baseline_version", "")
    target_ver = meta.get("target_version", "")

    has_detail = any(d.get("baseline_url") for d in diffs)
    di_json = _json.dumps(diff_ignore or {}, ensure_ascii=False)
    di_cfg = load_diff_ignore(diff_ignore) if diff_ignore else DiffIgnoreConfig()
    canonical_path = str((repo_root / "diff_ignore.json").resolve()) if repo_root else ""
    canonical_json = _json.dumps(canonical_path)

    diff_rows = []
    popup_data = []
    for idx, d in enumerate(diffs):
        row_scenario = d.get("scenario", "")
        row_step_seq = d.get("step_seq")
        val_match = d.get("value_match", 1)

        # Render the raw comparison result. SO-suppression is applied in JS at view time
        # so popup toggles update the row immediately without a re-run.
        status_icon = "✓" if d["status_match"] else "✗"
        status_color = "#4ade80" if d["status_match"] else "#ef4444"
        struct_icon = "✓" if d["structure_match"] else "✗"
        struct_color = "#4ade80" if d["structure_match"] else "#ef4444"
        val_icon = "✓" if val_match else "✗"
        val_color = "#4ade80" if val_match else "#f59e0b"
        detail = d.get("diff_summary", "") or ""
        val_diff = d.get("value_diff", "") or ""

        has_diff_content = bool(detail or val_diff)
        diff_count = val_diff.count("\n") + 1 if val_diff else 0

        b_status = d.get("baseline_status", "")
        t_status = d.get("target_status", "")
        step_seq = row_step_seq
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

        # Path cell: when baseline and target URLs diverge in path (after stripping
        # query strings — those go in the popup), show both paths stacked.
        b_url = d.get("baseline_url") or ""
        t_url = d.get("target_url") or ""
        b_path = urlparse(b_url).path if b_url else ""
        t_path = urlparse(t_url).path if t_url else ""
        if b_path and t_path and b_path != t_path:
            path_cell_html = (
                f'<td class="cell-path"><div>{_esc(b_path)}</div>'
                f'<div class="path-diverge">{_esc(t_path)}</div></td>'
            )
        else:
            path_cell_html = f'<td class="cell-path">{_esc(d["path"])}</td>'

        popup_entry: dict[str, Any] = {
            "method": d["method"],
            "path": d["path"],
            "scenario": row_scenario,
            "step_seq": step_seq,
            "step_label": step_label,
            "diff_summary": detail,
            "value_diff": val_diff,
            # header_diff is small and always meaningful — included regardless of --detail
            "header_diff": d.get("header_diff") or "",
        }
        if has_detail:
            popup_entry.update({
                "baseline_url": d.get("baseline_url") or "",
                "target_url": d.get("target_url") or "",
                "baseline_request": d.get("baseline_request") or "",
                "baseline_response": d.get("baseline_response") or "",
                "baseline_request_headers": d.get("baseline_request_headers") or "",
                "baseline_response_headers": d.get("baseline_response_headers") or "",
                "target_request": d.get("target_request") or "",
                "target_response": d.get("target_response") or "",
                "target_request_headers": d.get("target_request_headers") or "",
                "target_response_headers": d.get("target_response_headers") or "",
                "baseline_timestamp": d.get("baseline_timestamp") or "",
                "target_timestamp": d.get("target_timestamp") or "",
                "baseline_duration": d.get("baseline_duration"),
                "target_duration": d.get("target_duration"),
            })
        popup_data.append(popup_entry)

        # Details cell — always clickable so users can open popup to manage rules
        # even on rule-suppressed rows. Optional diff-badge + JS-populated row-labels
        # (SO/ADDED/REMOVED) + placeholder dash that JS hides when labels exist.
        badge_html = (
            f'<span class="diff-badge">{diff_count} diff{"s" if diff_count != 1 else ""}</span>'
            if has_diff_content else ''
        )
        empty_html = '' if has_diff_content else '<span class="row-empty" style="color:#555">—</span>'
        detail_cell = (
            f'<td class="detail-trigger" onclick="openPopup({idx})">'
            f'{badge_html}<span class="row-labels"></span>{empty_html}'
            f'</td>'
        )

        row_types = []
        if not d["status_match"]:
            row_types.append("status")
        if not d["structure_match"]:
            row_types.append("structure")
        if not val_match:
            row_types.append("value")
        data_diff_types = " ".join(row_types) if row_types else "clean"

        # Δms (target - baseline duration) — perf regression signal per call
        b_dur = d.get("baseline_duration")
        t_dur = d.get("target_duration")
        if b_dur is not None and t_dur is not None:
            delta_ms = t_dur - b_dur
            if abs(delta_ms) < 5:
                delta_class = "delta-jitter"
            elif delta_ms > 0:
                delta_class = "delta-slower"
            else:
                delta_class = "delta-faster"
            sign = "+" if delta_ms > 0 else ""
            delta_display = f"{sign}{delta_ms}"
            data_delta = str(delta_ms)
        else:
            delta_class = "delta-jitter"
            delta_display = "—"
            data_delta = ""

        row = (
            f'<tr class="diff-row" data-method="{d["method"]}" data-path="{_esc(d["path"].lower())}"'
            f' data-scenario="{_esc(_display_scenario(row_scenario).lower())}" data-status="{b_status} {t_status}"'
            f' data-step="{_esc(step_display.lower())}"'
            f' data-raw-scenario="{_esc(row_scenario)}" data-raw-path="{_esc(d["path"])}"'
            f' data-step-seq="{step_seq if step_seq is not None else ""}"'
            f' data-duration-delta="{data_delta}"'
            f' data-orig-structure="{1 if d["structure_match"] else 0}"'
            f' data-orig-value="{1 if val_match else 0}"'
            f' data-diff-types="{data_diff_types}">'
            f'<td style="color:#666">{idx + 1}</td>'
            f'<td class="cell-scenario">{_display_scenario(row_scenario)}</td>'
            f'<td class="cell-step">{_esc(step_display)}</td>'
            f'<td class="cell-timing">{timing_display}</td>'
            f'<td class="cell-delta {delta_class}">{delta_display}</td>'
            f'<td>{d["method"]}</td>'
            f'{path_cell_html}'
            f'<td style="color:{status_color}">{status_icon} {d.get("baseline_status", "")}'
            f'{"→" + str(d.get("target_status", "")) if not d["status_match"] else ""}</td>'
            f'<td class="cell-structure" style="color:{struct_color}">{struct_icon}</td>'
            f'<td class="cell-value" style="color:{val_color}">{val_icon}</td>'
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
            f'<td class="cell-path">{_esc(m["path"])}</td>'
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
  .cell-delta {{ font-size: 12px; font-family: 'SF Mono', monospace; white-space: nowrap; text-align: right; }}
  .cell-delta.delta-slower {{ color: #ef4444; }}
  .cell-delta.delta-faster {{ color: #4ade80; }}
  .cell-delta.delta-jitter {{ color: #555; }}
  .cell-path {{ font-family: 'SF Mono', monospace; }}
  .path-diverge {{ color: #f59e0b; margin-top: 2px; }}
  .detail-trigger {{ cursor: pointer; }}
  .detail-trigger:hover .diff-badge {{ background: #334155; }}
  .diff-badge {{ font-size: 12px; color: #f59e0b; background: #1e293b; padding: 2px 8px; border-radius: 4px; }}
  .row-labels {{ display: inline-flex; gap: 4px; margin-left: 6px; vertical-align: middle; }}
  .row-label {{
    font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 3px; letter-spacing: 0.5px;
  }}
  .row-label-so {{ background: #134e4a; color: #5eead4; }}
  .row-label-added {{ background: #14532d; color: #6ee7b7; }}
  .row-label-removed {{ background: #7f1d1d; color: #fca5a5; }}

  /* SO button (rendered inside popup) */
  .so-btn {{
    padding: 6px 14px; font-size: 12px; font-weight: 600; border-radius: 4px; cursor: pointer;
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
  .known-btn {{
    display: inline-block; padding: 2px 8px; margin: 2px; font-size: 11px;
    font-family: 'SF Mono', monospace; border-radius: 4px; cursor: pointer;
    border: 1px solid #555; background: #1a1a1a; color: #a78bfa; transition: all 0.15s;
  }}
  .known-btn:hover {{ color: #c4b5fd; border-color: #7c3aed; }}
  .known-btn.is-known {{ background: #5b21b6; color: #fff; border-color: #7c3aed; }}

  /* Tabs */
  .tabs {{
    display: flex; gap: 4px; border-bottom: 1px solid #333; margin: 24px 0 16px;
  }}
  .tab-btn {{
    padding: 10px 18px; background: transparent; border: none;
    border-bottom: 2px solid transparent; color: #888;
    font-size: 14px; font-weight: 600; cursor: pointer; margin-bottom: -1px;
  }}
  .tab-btn:hover {{ color: #ccc; }}
  .tab-btn.active {{ color: #e5e5e5; border-bottom-color: #0d9488; }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}
  #tab-config {{ position: relative; }}
  #tab-config .download-btn {{
    position: absolute; top: 8px; right: 12px; z-index: 2; margin: 0;
  }}

  /* Config editor */
  .config-editor {{
    font-family: 'SF Mono', monospace; font-size: 13px; line-height: 1.5;
    background: #0a0a0a; border: 1px solid #222; border-radius: 6px;
    padding: 48px 16px 16px 16px; /* top padding leaves room for floating Download button */
    width: 100%; min-height: calc(100vh - 320px); resize: vertical;
    color: #ccc; tab-size: 2; outline: none; box-sizing: border-box;
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
  .popup-detail-tabs {{
    display: flex; gap: 4px; border-bottom: 1px solid #333; margin-bottom: 12px;
  }}
  .popup-tab-btn {{
    padding: 8px 16px; background: transparent; border: none;
    border-bottom: 2px solid transparent; color: #888;
    font-size: 13px; font-weight: 600; cursor: pointer; margin-bottom: -1px;
  }}
  .popup-tab-btn:hover {{ color: #ccc; }}
  .popup-tab-btn.active {{ color: #e5e5e5; border-bottom-color: #0d9488; }}
  .popup-detail-pane {{ display: none; }}
  .popup-detail-pane.active {{ display: block; }}
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
var TARGET_VERSION = '{_esc(target_ver)}';
var CANONICAL_PATH = {canonical_json};  // Absolute path to repo's diff_ignore.json (empty if unknown)
var DI_CHANGED = false;

// -- diff_ignore helpers --

function diFields() {{ return DI.fields || []; }}
function diStatusOnly() {{ return DI.status_only || []; }}

function diHasField(name) {{ return diFields().indexOf(name) !== -1; }}

function _fnmatch(value, pattern) {{
  // Treat null/undefined pattern as wildcard so partial diff_ignore.json entries
  // (e.g. status_only with only step_seq) match anything for the missing fields.
  // Matches the Python loader's behavior of defaulting missing fields to "*".
  if (pattern == null || pattern === '*') return true;
  if (pattern.indexOf('*') === -1) return value === pattern;
  var re = '^' + pattern.replace(/[.+^${{}}()|[\\]\\\\]/g, '\\\\$&').replace(/\\*/g, '[^/]*') + '$';
  return new RegExp(re).test(value);
}}
// Split a "METHOD /path" endpoint string into [method, path]. Lone path → ["*", path].
function _splitEndpoint(endpoint) {{
  if (!endpoint) return ['*', '*'];
  var s = String(endpoint).trim();
  var idx = s.indexOf(' ');
  if (idx === -1) return ['*', s || '*'];
  return [(s.slice(0, idx).trim() || '*'), (s.slice(idx + 1).trim() || '*')];
}}

function diHasStatusOnly(method, path, scenario, stepSeq) {{
  return diStatusOnly().some(function(r) {{
    // New form: r.endpoint = "METHOD /path". Legacy form: r.path with implicit method=*.
    var rMethod, rPath;
    if (r.endpoint) {{
      var parts = _splitEndpoint(r.endpoint);
      rMethod = parts[0]; rPath = parts[1];
    }} else {{
      rMethod = '*'; rPath = r.path;
    }}
    return _fnmatch((method || '').toUpperCase(), (rMethod || '*').toUpperCase())
      && _fnmatch(path, rPath)
      && _fnmatch(scenario, r.scenario || '*')
      && _stepSeqMatches(r.step_seq || '*', stepSeq);
  }});
}}
function _stepSeqMatches(pattern, seq) {{
  if (pattern === '*') return true;
  if (!seq && seq !== '0') return false;
  var s = String(pattern);
  if (s.indexOf('-') !== -1) {{
    var parts = s.split('-');
    return Number(seq) >= Number(parts[0]) && Number(seq) <= Number(parts[1]);
  }}
  return String(seq) === s;
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

// Canonicalize a JSON path so that concrete array indices ([0], [42]), xpath-style
// wildcards ([*]), and jsonpath-style wildcards ([]) all compare as equal. Both
// stored rules and diff-line paths run through this for lookup, so all three forms
// match each other.
function _canonicalKcPath(p) {{
  return (p || '').replace(/\\[\\d+\\]/g, '[*]').replace(/\\[\\]/g, '[*]');
}}

function diHasKnownChange(endpoint, fieldPath, change) {{
  var target = _canonicalKcPath(fieldPath);
  return (DI.known_changes || []).some(function(kc) {{
    return kc.endpoint === endpoint
      && _canonicalKcPath(kc.path) === target
      && kc.change === change;
  }});
}}

function diAddKnownChange(endpoint, fieldPath, change, since) {{
  if (!DI.known_changes) DI.known_changes = [];
  if (!diHasKnownChange(endpoint, fieldPath, change)) {{
    // Store canonical [*] form so the rule generalizes across array indices.
    DI.known_changes.push({{
      endpoint: endpoint,
      path: _canonicalKcPath(fieldPath),
      change: change,
      since: since,
    }});
  }}
  diOnChange();
}}

function diRemoveKnownChange(endpoint, fieldPath, change) {{
  if (!DI.known_changes) return;
  var target = _canonicalKcPath(fieldPath);
  DI.known_changes = DI.known_changes.filter(function(kc) {{
    return !(kc.endpoint === endpoint
      && _canonicalKcPath(kc.path) === target
      && kc.change === change);
  }});
  diOnChange();
}}

function toggleKnownChange(btn, endpoint, fieldPath, change) {{
  if (btn.classList.contains('is-known')) {{
    diRemoveKnownChange(endpoint, fieldPath, change);
    btn.classList.remove('is-known');
  }} else {{
    diAddKnownChange(endpoint, fieldPath, change, TARGET_VERSION);
    btn.classList.add('is-known');
  }}
  updateRowLabels();
}}

function diAddStatusOnly(method, path, scenario, stepSeq) {{
  if (!DI.status_only) DI.status_only = [];
  if (!diHasStatusOnly(method, path, scenario, stepSeq)) {{
    // Write the new `endpoint` form, mirroring known_changes shape.
    DI.status_only.push({{
      endpoint: (method || '*').toUpperCase() + ' ' + path,
      scenario: scenario,
      step_seq: stepSeq,
    }});
  }}
  diOnChange();
}}

function diRemoveStatusOnly(method, path, scenario, stepSeq) {{
  if (!DI.status_only) return;
  var endpoint = (method || '*').toUpperCase() + ' ' + path;
  DI.status_only = DI.status_only.filter(function(r) {{
    // Match either new `endpoint` form OR legacy `path`-only form (for files
    // that haven't been auto-upgraded yet).
    var rEndpoint = r.endpoint || ('* ' + (r.path || '*'));
    return !(rEndpoint === endpoint
      && (r.scenario || '*') === scenario
      && String(r.step_seq || '*') === String(stepSeq));
  }});
  diOnChange();
}}

function diOnChange() {{
  DI_CHANGED = true;
  document.getElementById('config-json').value = JSON.stringify(DI, null, 2);
  document.getElementById('config-error').textContent = '';
  var marker = document.getElementById('changed-marker');
  if (marker) marker.style.display = 'inline';
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
      updateRowLabels();
    }} catch(e) {{
      errEl.textContent = 'Invalid JSON: ' + e.message;
    }}
  }});
}});

async function downloadDI() {{
  var data = JSON.stringify(DI, null, 2) + '\\n';
  var defaultName = 'diff_ignore.json';
  // Canonical hint surfaces the repo path so users know where the file is meant to live.
  // Browsers strip path separators from suggestedName/download for security, so the path
  // is informational only; the default filename remains the basename.
  var canonicalSuffix = CANONICAL_PATH ? ' \\u2014 canonical: ' + CANONICAL_PATH : '';
  if (window.showSaveFilePicker) {{
    try {{
      var handle = await window.showSaveFilePicker({{
        suggestedName: defaultName,
        types: [{{ description: 'diff_ignore.json', accept: {{ 'application/json': ['.json'] }} }}],
      }});
      var writable = await handle.createWritable();
      await writable.write(data);
      await writable.close();
      showToast('Downloaded ' + handle.name + canonicalSuffix);
      return;
    }} catch (e) {{
      if (e && e.name === 'AbortError') return;
      // Other errors (SecurityError on file://, etc): fall through to prompt.
    }}
  }}
  var label = CANONICAL_PATH
    ? 'Save as (canonical: ' + CANONICAL_PATH + '):'
    : 'Save as:';
  var name = window.prompt(label, defaultName);
  if (name === null) return;
  name = name.trim() || defaultName;
  if (!/\\.json$/i.test(name)) name += '.json';
  var blob = new Blob([data], {{ type: 'application/json' }});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast('Downloaded ' + name + canonicalSuffix);
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

var _ID_RE = /^[0-9]+$|^[0-9a-f]{{8}}-[0-9a-f]{{4}}-|^[a-z]+_[a-z0-9_]+$|.*[0-9]{{4,}}.*/i;
function templatizePath(p) {{
  return p.split('/').map(function(s) {{ return s && _ID_RE.test(s) ? '*' : s; }}).join('/');
}}

function toggleSO(btn) {{
  var method = (btn.dataset.method || '*').toUpperCase();
  var path = templatizePath(btn.dataset.path);
  var scenario = btn.dataset.scenario;
  var stepSeq = btn.dataset.stepSeq;
  if (btn.classList.contains('is-active')) {{
    diRemoveStatusOnly(method, path, scenario, stepSeq);
    btn.classList.remove('is-active');
    btn.title = 'Add to status_only';
    btn.textContent = 'Mark as status_only';
  }} else {{
    diAddStatusOnly(method, path, scenario, stepSeq);
    btn.classList.add('is-active');
    btn.title = 'Remove from status_only';
    btn.textContent = '✓ status_only';
  }}
  updateRowLabels();
}}

// -- Row labels (SO / ADDED / REMOVED) reflect current DI state --
function computeRowLabels(row) {{
  var labels = [];
  var path = templatizePath(row.dataset.rawPath);
  var scenario = row.dataset.rawScenario || '*';
  var stepSeq = row.dataset.stepSeq || '*';
  // SO label only when the rule is doing real work — if structure and value
  // both already match, SO has nothing to suppress and showing the label is misleading.
  var origStruct = row.dataset.origStructure === '1';
  var origValue = row.dataset.origValue === '1';
  var fullyEqual = origStruct && origValue;
  var method = (row.dataset.method || '*').toUpperCase();
  if (!fullyEqual && diHasStatusOnly(method, path, scenario, stepSeq)) labels.push('SO');
  var endpoint = method + ' ' + path;
  var hasAdded = false, hasRemoved = false;
  (DI.known_changes || []).forEach(function(kc) {{
    if (kc.endpoint !== endpoint) return;
    if (kc.change === 'added') hasAdded = true;
    else if (kc.change === 'removed') hasRemoved = true;
  }});
  if (hasAdded) labels.push('ADDED');
  if (hasRemoved) labels.push('REMOVED');
  return labels;
}}
function updateRowLabels() {{
  document.querySelectorAll('.diff-row').forEach(function(row) {{
    var labels = computeRowLabels(row);
    var span = row.querySelector('.row-labels');
    if (span) {{
      span.innerHTML = labels.map(function(L) {{
        return '<span class="row-label row-label-' + L.toLowerCase() + '">' + L + '</span>';
      }}).join('');
    }}

    // Apply SO suppression to structure / value / diff-badge cells, but only
    // when SO is doing real work. Logic: full equality (structure AND value
    // both match originally) wins regardless of SO — show ✓✓ because there's
    // nothing to suppress. Only when SO is silencing a real diff do we show —.
    var path = templatizePath(row.dataset.rawPath);
    var scenario = row.dataset.rawScenario || '*';
    var stepSeq = row.dataset.stepSeq || '*';
    var method = (row.dataset.method || '*').toUpperCase();
    var soActive = diHasStatusOnly(method, path, scenario, stepSeq);
    var origStruct = row.dataset.origStructure === '1';
    var origValue = row.dataset.origValue === '1';
    var fullyEqual = origStruct && origValue;
    var structCell = row.querySelector('.cell-structure');
    var valueCell = row.querySelector('.cell-value');
    var badge = row.querySelector('.diff-badge');
    if (soActive && !fullyEqual) {{
      // SO is genuinely suppressing a structure or value diff — show —
      if (structCell) {{ structCell.textContent = '\\u2014'; structCell.style.color = '#555'; }}
      if (valueCell) {{ valueCell.textContent = '\\u2014'; valueCell.style.color = '#555'; }}
      if (badge) badge.style.display = 'none';
    }} else {{
      // Either SO inactive, or SO active but the comparison is naturally clean.
      // Restore original ✓/✗ from data attrs.
      if (structCell) {{
        structCell.textContent = origStruct ? '\\u2713' : '\\u2717';
        structCell.style.color = origStruct ? '#4ade80' : '#ef4444';
      }}
      if (valueCell) {{
        valueCell.textContent = origValue ? '\\u2713' : '\\u2717';
        valueCell.style.color = origValue ? '#4ade80' : '#f59e0b';
      }}
      if (badge) badge.style.display = '';
    }}

    var empty = row.querySelector('.row-empty');
    // Show — placeholder only if no badge AND no labels AND nothing else in the cell.
    // When SO is active, diff-badge is hidden so we may need to show row-empty.
    if (empty) {{
      var badgeVisible = badge && badge.style.display !== 'none';
      empty.style.display = (labels.length > 0 || badgeVisible) ? 'none' : '';
    }}
  }});
}}

// -- Response-header ignore --

function diHeaderIgnore() {{ return DI.header_ignore || []; }}
function diHasHeaderIgnore(name) {{ return diHeaderIgnore().indexOf(name.toLowerCase()) !== -1; }}
function diAddHeaderIgnore(name) {{
  if (!DI.header_ignore) DI.header_ignore = [];
  var lc = name.toLowerCase();
  if (DI.header_ignore.indexOf(lc) === -1) DI.header_ignore.push(lc);
  diOnChange();
}}
function diRemoveHeaderIgnore(name) {{
  if (!DI.header_ignore) return;
  var lc = name.toLowerCase();
  DI.header_ignore = DI.header_ignore.filter(function(h) {{ return h !== lc; }});
  diOnChange();
}}
function toggleHeaderIgnore(btn, name) {{
  if (btn.classList.contains('is-ignored')) {{
    diRemoveHeaderIgnore(name);
    btn.classList.remove('is-ignored');
    document.querySelectorAll('.field-btn[data-header="' + name + '"]').forEach(function(b) {{ b.classList.remove('is-ignored'); }});
  }} else {{
    diAddHeaderIgnore(name);
    btn.classList.add('is-ignored');
    document.querySelectorAll('.field-btn[data-header="' + name + '"]').forEach(function(b) {{ b.classList.add('is-ignored'); }});
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


// -- Filtering --
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
  if (d.header_diff) {{
    html += '<div class="popup-section">Header Diff</div>';
    html += '<div class="popup-diff">' + d.header_diff.split('\\n').map(colorDiffLine).join('\\n') + '</div>';
    // Per-header ignore buttons, parsed from the diff lines.
    var hdrSeen = {{}};
    var hdrBtns = [];
    d.header_diff.split('\\n').forEach(function(line) {{
      var m = line.match(/^[+\\-~]\\s+([^:]+):/);
      if (!m) return;
      var hname = m[1].trim().toLowerCase();
      if (!hname || hdrSeen[hname]) return;
      hdrSeen[hname] = true;
      var hcls = diHasHeaderIgnore(hname) ? 'field-btn is-ignored' : 'field-btn';
      hdrBtns.push('<button class="' + hcls + '" data-header="' + esc(hname) + '" onclick="toggleHeaderIgnore(this, \\'' + esc(hname).replace(/'/g, "\\\\'") + '\\')">' + esc(hname) + '</button>');
    }});
    if (hdrBtns.length) {{
      html += '<div class="popup-section">Ignore Headers</div><div>' + hdrBtns.join('') + '</div>';
    }}
  }}
  // Known change buttons from both structure and value diff
  if (TARGET_VERSION) {{
    var kcBtns = [];
    var kcEndpoint = d.method + ' ' + templatizePath(d.path);
    var allDiffLines = ((d.diff_summary || '') + '\\n' + (d.value_diff || '')).split('\\n');
    var kcSeen = {{}};
    allDiffLines.forEach(function(line) {{
      var m = line.match(/^([+-])\\s+(\\$\\S+?):/);
      if (!m) return;
      var change = m[1] === '+' ? 'added' : 'removed';
      var fieldPath = m[2];
      var key = change + ':' + fieldPath;
      if (kcSeen[key]) return;
      kcSeen[key] = true;
      var label = (change === 'added' ? 'Added' : 'Removed') + ' in ' + TARGET_VERSION;
      var cls = diHasKnownChange(kcEndpoint, fieldPath, change) ? 'known-btn is-known' : 'known-btn';
      kcBtns.push('<button class="' + cls + '" onclick="toggleKnownChange(this, \\'' + esc(kcEndpoint).replace(/'/g, "\\\\'") + '\\', \\'' + esc(fieldPath).replace(/'/g, "\\\\'") + '\\', \\'' + change + '\\')">' + esc(label) + ' (' + esc(fieldPath) + ')</button>');
    }});
    if (kcBtns.length) {{
      html += '<div class="popup-section">Known Changes (' + esc(kcEndpoint) + ')</div><div>' + kcBtns.join('') + '</div>';
    }}
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
  // Status-only toggle — coarse-grained "ignore body diffs, check status only".
  // Always shown when popup is open (popup is only open on rows with diffs).
  var soMethod = (d.method || '*').toUpperCase();
  var soPath = templatizePath(d.path);
  var soScenario = d.scenario || '*';
  var soStepSeq = (d.step_seq != null) ? d.step_seq : '*';
  var soActive = diHasStatusOnly(soMethod, soPath, soScenario, soStepSeq);
  var soCls = 'so-btn' + (soActive ? ' is-active' : '');
  var soTitle = soActive ? 'Remove from status_only' : 'Add to status_only';
  html += '<div class="popup-section">Status Only</div>';
  html += '<div><button class="' + soCls + '" '
       + 'data-method="' + esc(soMethod) + '" '
       + 'data-path="' + esc(d.path) + '" '
       + 'data-scenario="' + esc(d.scenario || '*') + '" '
       + 'data-step-seq="' + esc(String(soStepSeq)) + '" '
       + 'onclick="toggleSO(this)" title="' + soTitle + '">'
       + (soActive ? '\\u2713 status_only' : 'Mark as status_only') + '</button></div>';
  // Detail panels (Baseline / Target tabs). Render whenever *either* side has
  // detail — otherwise rows where only one side has a record (e.g. added or
  // removed endpoints) would show no body at all.
  var hasBaselineDetail = d.baseline_url !== undefined && d.baseline_url !== null;
  var hasTargetDetail = d.target_url !== undefined && d.target_url !== null;
  if (hasBaselineDetail || hasTargetDetail) {{
    var bDur = d.baseline_duration != null ? d.baseline_duration + 'ms' : '';
    var tDur = d.target_duration != null ? d.target_duration + 'ms' : '';
    html += '<div class="popup-section">Request / Response</div>';
    html += '<div class="popup-detail-tabs" role="tablist">';
    // Default the active tab to the side that has data
    var activeBaseline = hasBaselineDetail;
    html += '<button class="popup-tab-btn' + (activeBaseline ? ' active' : '') + '" role="tab" onclick="switchPopupDetail(this, \\'baseline\\')">Baseline' + (hasBaselineDetail ? '' : ' (no record)') + '</button>';
    html += '<button class="popup-tab-btn' + (activeBaseline ? '' : ' active') + '" role="tab" onclick="switchPopupDetail(this, \\'target\\')">Target' + (hasTargetDetail ? '' : ' (no record)') + '</button>';
    html += '</div>';

    // Render a side. When the side has no record at all, show a placeholder.
    // When it has a record but the response body is empty (304 / 204 / some
    // 4xx-5xx), the existing formatJson "<em>empty</em>" already covers it.
    function renderSide(side, hasDetail) {{
      var paneCls = 'popup-detail-pane' + (
        (side === 'baseline' && activeBaseline) || (side === 'target' && !activeBaseline)
          ? ' active' : ''
      );
      var html = '<div class="' + paneCls + '" data-side="' + side + '" role="tabpanel">';
      if (!hasDetail) {{
        var otherSide = side === 'baseline' ? 'Target' : 'Baseline';
        html += '<div class="popup-meta" style="color:#a3a3a3">(no record on this side — only ' + otherSide + ' fired this call)</div>';
        html += '</div>';
        return html;
      }}
      var dur = d[side + '_duration'] != null ? d[side + '_duration'] + 'ms' : '';
      html += '<div class="popup-meta">' + esc(d[side + '_timestamp'] || '') + (dur ? '&nbsp;&nbsp;' + dur : '') + '</div>';
      html += '<div class="popup-url">' + esc(d[side + '_url'] || '') + '</div>';
      html += '<div class="popup-label">Request Headers</div><pre class="popup-body">' + formatJson(d[side + '_request_headers']) + '</pre>';
      html += '<div class="popup-label">Request</div><pre class="popup-body">' + formatJson(d[side + '_request']) + '</pre>';
      html += '<div class="popup-label">Response Headers</div><pre class="popup-body">' + formatJson(d[side + '_response_headers']) + '</pre>';
      html += '<div class="popup-label">Response</div><pre class="popup-body">' + formatJson(d[side + '_response']) + '</pre>';
      html += '</div>';
      return html;
    }}

    html += renderSide('baseline', hasBaselineDetail);
    html += renderSide('target', hasTargetDetail);
  }}
  content.innerHTML = html;
  el.classList.add('open');
}}
function closePopup() {{
  document.getElementById('popup-overlay').classList.remove('open');
}}
function switchPopupDetail(btn, side) {{
  var tabs = btn.parentElement;
  tabs.querySelectorAll('.popup-tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
  var container = tabs.parentElement;
  container.querySelectorAll('.popup-detail-pane').forEach(function(p) {{
    p.classList.toggle('active', p.dataset.side === side);
  }});
}}
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closePopup(); }});
var _activeType = 'all';
function filterByType(type) {{
  switchTab('comparison');
  _activeType = type;
  try {{ localStorage.setItem('scout-diff-active-type', type); }} catch (e) {{}}
  document.querySelectorAll('.summary .badge').forEach(function(b) {{ b.classList.remove('active'); }});
  event.target.classList.add('active');
  applyFilters();
}}

function switchTab(name) {{
  document.querySelectorAll('.tab-btn').forEach(function(b) {{
    b.classList.toggle('active', b.dataset.tab === name);
  }});
  document.querySelectorAll('.tab-pane').forEach(function(p) {{
    p.classList.toggle('active', p.id === 'tab-' + name);
  }});
  try {{ localStorage.setItem('scout-diff-tab', name); }} catch (e) {{}}
}}

document.addEventListener('DOMContentLoaded', function() {{
  try {{
    var savedTab = localStorage.getItem('scout-diff-tab');
    if (savedTab) switchTab(savedTab);

    var savedKw = localStorage.getItem('scout-diff-filter-kw');
    if (savedKw) document.getElementById('filter-input').value = savedKw;

    var savedField = localStorage.getItem('scout-diff-filter-field');
    if (savedField) document.getElementById('filter-field').value = savedField;

    var savedType = localStorage.getItem('scout-diff-active-type');
    if (savedType) {{
      _activeType = savedType;
      document.querySelectorAll('.summary .badge').forEach(function(b) {{
        b.classList.toggle('active', b.dataset.type === savedType);
      }});
    }}

    var savedSort = localStorage.getItem('scout-diff-sort');
    if (savedSort) {{
      var sortEl = document.getElementById('sort-mode');
      if (sortEl) {{
        sortEl.value = savedSort;
        applySort();
      }}
    }}
  }} catch (e) {{}}
  applyFilters();
  updateRowLabels();
}});
function filterRows(q) {{ applyFilters(); }}
function applyFilters() {{
  var kw = (document.getElementById('filter-input').value || '').trim();
  var field = document.getElementById('filter-field').value;
  try {{
    localStorage.setItem('scout-diff-filter-kw', kw);
    localStorage.setItem('scout-diff-filter-field', field);
  }} catch (e) {{}}
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

// -- Sort: re-orders <tr> elements in tbody by data-duration-delta. --
// Rows with no delta (missing duration on either side) sink to the bottom for both
// asc and desc — they carry no signal for a latency view.
function applySort() {{
  var mode = document.getElementById('sort-mode').value;
  try {{ localStorage.setItem('scout-diff-sort', mode); }} catch (e) {{}}
  var tbody = document.querySelector('#tab-comparison table tbody');
  if (!tbody) return;
  var rows = Array.from(tbody.querySelectorAll('tr.diff-row'));
  if (mode === 'default') {{
    // Restore original order via the # column (data-original-index would be cleaner;
    // for now, sort by the visible "#" cell text which is monotonic).
    rows.sort(function(a, b) {{
      var ai = parseInt(a.firstElementChild ? a.firstElementChild.textContent : '0', 10) || 0;
      var bi = parseInt(b.firstElementChild ? b.firstElementChild.textContent : '0', 10) || 0;
      return ai - bi;
    }});
  }} else {{
    var direction = mode === 'delta-desc' ? -1 : 1;
    rows.sort(function(a, b) {{
      var av = a.dataset.durationDelta;
      var bv = b.dataset.durationDelta;
      var aMissing = av === '' || av === undefined;
      var bMissing = bv === '' || bv === undefined;
      if (aMissing && bMissing) return 0;
      if (aMissing) return 1;   // sink missing
      if (bMissing) return -1;
      return direction * (parseFloat(av) - parseFloat(bv));
    }});
  }}
  rows.forEach(function(row) {{ tbody.appendChild(row); }});
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
  <span class="badge active" data-type="all" onclick="filterByType('all')">All ({summary['total_paired']})</span>
  <span class="badge" data-type="status" style="color:#ef4444" onclick="filterByType('status')">{summary['status_mismatches']} status</span>
  <span class="badge" data-type="structure" style="color:#ef4444" onclick="filterByType('structure')">{summary['structure_mismatches']} structure</span>
  <span class="badge" data-type="value" style="color:#f59e0b" onclick="filterByType('value')">{value_changes} value</span>
  <span class="badge" data-type="endpoint" style="color:#facc15" onclick="filterByType('endpoint')">{summary['missing_endpoints']} endpoint</span>
</div>
<div class="summary">
  <span>Baseline: {summary.get('baseline_4xx', 0)} 4xx, {summary.get('baseline_5xx', 0)} 5xx</span>
  <span>Target: {summary.get('target_4xx', 0)} 4xx, {summary.get('target_5xx', 0)} 5xx</span>
</div>

<div class="tabs" role="tablist">
  <button class="tab-btn active" data-tab="comparison" role="tab" onclick="switchTab('comparison')">Endpoints</button>
  <button class="tab-btn" data-tab="config" role="tab" onclick="switchTab('config')">Ignore rules <span id="changed-marker" class="changed-marker" style="display:none">● modified</span></button>
</div>

<section class="tab-pane active" id="tab-comparison" role="tabpanel">
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
    <select id="sort-mode" onchange="applySort()"
      style="padding:6px 8px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e5e5e5;font-size:13px;"
      title="Sort by latency delta (target - baseline)">
      <option value="default">Default order</option>
      <option value="delta-desc">Δms ↓ (slower first)</option>
      <option value="delta-asc">Δms ↑ (faster first)</option>
    </select>
    <span id="filter-count" style="font-size:12px;color:#888;"></span>
  </div>
  <table>
  <thead><tr><th>#</th><th>Scenario</th><th>Step</th><th>ms</th><th title="target_duration - baseline_duration">Δms</th><th>Method</th><th>Path</th><th>Status</th><th>Structure</th><th>Value</th><th>Details</th></tr></thead>
  <tbody>
  {"".join(diff_rows) if diff_rows else '<tr><td colspan="11" style="color:#888">No paired endpoints</td></tr>'}
  </tbody>
  </table>
  {"<h2>Endpoint Changes</h2>" + chr(10) + '<table>' + chr(10) + '<thead><tr><th>#</th><th>Scenario</th><th>Change</th><th>Method</th><th>Path</th><th>Status</th></tr></thead>' + chr(10) + '<tbody>' + chr(10) + "".join(missing_rows) + chr(10) + '</tbody>' + chr(10) + '</table>' if missing_rows else ""}
</section>

<section class="tab-pane" id="tab-config" role="tabpanel">
  <button class="download-btn" onclick="downloadDI()">Download diff_ignore.json</button>
  <textarea id="config-json" class="config-editor" spellcheck="false">{_esc(_json.dumps(diff_ignore or {}, indent=2, ensure_ascii=False))}</textarea>
  <div id="config-error" class="config-error"></div>
</section>

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
