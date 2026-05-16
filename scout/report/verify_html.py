"""Verify report — self-contained HTML with thumbnail grid + lightbox."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scout.runner.executor import ExecutionResult


def _img_data_uri(path: Path) -> str:
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _collect_screenshots(scenario_dir: Path) -> list[dict]:
    """Collect all screenshots as a flat list, sorted by filename."""
    ss_dir = scenario_dir / "screenshots"
    if not ss_dir.exists():
        return []

    shots = []
    for f in sorted(ss_dir.glob("*.png")):
        name = f.stem
        if name == "final":
            label = "Final"
        elif name == "error":
            label = "Error"
        elif len(name) == 3 and name.isdigit():
            step = int(name[:2])
            sub = int(name[2])
            label = f"Step {step} {'before' if sub == 1 else 'after'}"
        else:
            label = name
        shots.append({"label": label, "path": f})
    return shots


def generate_verify_html(
    results: dict[str, ExecutionResult],
    output_path: Path,
    *,
    results_dir: Path,
    app_name: str = "",
    wall_ms: int | None = None,
) -> None:
    passed = sum(1 for r in results.values() if r.success)
    failed = len(results) - passed
    total_ms = wall_ms if wall_ms is not None else sum(r.duration_ms for r in results.values())
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build scenario data
    scenarios = []
    for i, (path, result) in enumerate(results.items()):
        scenario_dir = results_dir / path
        shots = _collect_screenshots(scenario_dir)
        scenarios.append(
            {
                "idx": i,
                "path": path,
                "display_name": path.replace("/", "."),
                "success": result.success,
                "status": "PASSED" if result.success else "FAILED",
                "color": "#4ade80" if result.success else "#ef4444",
                "duration": f"{result.duration_ms:,}ms",
                "errors": result.errors,
                "shots": shots,
            }
        )

    # Sidebar
    sidebar_items = []
    for s in scenarios:
        sidebar_items.append(
            f'<button class="nav-item" data-idx="{s["idx"]}" '
            f'onclick="selectScenario({s["idx"]})">'
            f'<span class="dot" style="background:{s["color"]}"></span>'
            f'<span class="nav-name">{s["display_name"]}</span>'
            f'<span class="nav-dur">{s["duration"]}</span>'
            f"</button>"
        )

    # Panels — each is a thumbnail grid
    panels = []
    for s in scenarios:
        errors_html = ""
        if s["errors"]:
            errs = "<br>".join(s["errors"])
            errors_html = f'<div class="error-banner">{errs}</div>'

        thumbs = []
        for j, shot in enumerate(s["shots"]):
            uri = _img_data_uri(shot["path"])
            thumbs.append(
                f'<div class="thumb" onclick="openLightbox({s["idx"]},{j})">'
                f'<img src="{uri}" loading="lazy">'
                f'<div class="thumb-label">{shot["label"]}</div>'
                f"</div>"
            )

        no_shots = '<div class="no-shots">No screenshots</div>' if not thumbs else ""

        panels.append(
            f'<div class="panel" data-idx="{s["idx"]}">'
            f'<div class="panel-header">'
            f"<h2>{s['display_name']}</h2>"
            f'<span class="badge" style="color:{s["color"]}">{s["status"]}</span>'
            f'<span class="dur">{s["duration"]}</span>'
            f"</div>"
            f"{errors_html}"
            f'<div class="grid">{"".join(thumbs)}</div>'
            f"{no_shots}"
            f"</div>"
        )

    # Build JS image index: scenarios[i] = [uri0, uri1, ...]
    # To avoid duplicating base64 in JS, we reference img elements in the DOM
    js_shot_counts = ",".join(str(len(s["shots"])) for s in scenarios)
    js_shot_labels = []
    for s in scenarios:
        labels = ",".join(f'"{shot["label"]}"' for shot in s["shots"])
        js_shot_labels.append(f"[{labels}]")
    js_labels_array = ",".join(js_shot_labels)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scout Verify — {app_name or "report"}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg-root: #08090a;
    --bg-surface: #0e1012;
    --bg-raised: #151719;
    --bg-hover: #1a1d20;
    --bg-active: #111d2e;
    --border: #1e2226;
    --border-light: #282d33;
    --text-primary: #e8eaed;
    --text-secondary: #9aa0a8;
    --text-tertiary: #6b7280;
    --accent: #5b9ef4;
    --green: #34d399;
    --red: #f87171;
    --font: 'DM Sans', -apple-system, system-ui, sans-serif;
    --mono: 'DM Mono', 'SF Mono', 'Fira Code', monospace;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--font); background: var(--bg-root); color: var(--text-primary); height: 100vh; display: flex; flex-direction: column; overflow: hidden; font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased; }}

  /* ── Header ── */
  .header {{ display: flex; align-items: center; gap: 24px; padding: 14px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; background: var(--bg-surface); }}
  .header h1 {{ font-size: 16px; font-weight: 700; white-space: nowrap; letter-spacing: -0.01em; }}
  .pills {{ display: flex; gap: 10px; font-size: 13px; font-family: var(--mono); }}
  .pill {{ padding: 4px 12px; border-radius: 6px; background: var(--bg-raised); border: 1px solid var(--border); color: var(--text-secondary); }}

  .layout {{ display: flex; flex: 1; overflow: hidden; }}

  /* ── Sidebar ── */
  .sidebar {{ width: 520px; min-width: 520px; border-right: 1px solid var(--border); overflow-y: auto; background: var(--bg-surface); }}
  .sidebar::-webkit-scrollbar {{ width: 6px; }}
  .sidebar::-webkit-scrollbar-thumb {{ background: #2a2d32; border-radius: 3px; }}
  .nav-item {{ display: flex; align-items: center; gap: 12px; width: 100%; padding: 14px 20px; border: none; border-left: 3px solid transparent; background: none; color: var(--text-secondary); cursor: pointer; text-align: left; font-size: 14px; font-family: var(--font); border-bottom: 1px solid var(--border); transition: background 0.12s, color 0.12s; }}
  .nav-item:hover {{ background: var(--bg-hover); color: var(--text-primary); }}
  .nav-item.active {{ background: var(--bg-active); border-left-color: var(--accent); color: var(--text-primary); }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .nav-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }}
  .nav-dur {{ color: var(--text-tertiary); font-size: 13px; font-family: var(--mono); flex-shrink: 0; }}

  /* ── Main ── */
  .main {{ flex: 1; overflow-y: auto; padding: 28px 32px; background: var(--bg-root); }}
  .main::-webkit-scrollbar {{ width: 6px; }}
  .main::-webkit-scrollbar-thumb {{ background: #2a2d32; border-radius: 3px; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .panel-header {{ display: flex; align-items: baseline; gap: 16px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }}
  .panel-header h2 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }}
  .badge {{ font-weight: 700; font-size: 14px; font-family: var(--mono); }}
  .dur {{ color: var(--text-tertiary); font-size: 14px; font-family: var(--mono); }}
  .error-banner {{ background: #1a0f0f; border: 1px solid #3d1f1f; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; font-size: 14px; color: var(--red); line-height: 1.6; }}

  /* ── Thumbnail grid ── */
  .grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
  .thumb {{ width: 450px; cursor: pointer; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); transition: border-color 0.15s, box-shadow 0.15s; background: var(--bg-surface); }}
  .thumb:hover {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }}
  .thumb img {{ display: block; width: 100%; }}
  .thumb-label {{ padding: 8px 12px; font-size: 13px; font-weight: 500; color: var(--text-secondary); background: var(--bg-raised); border-top: 1px solid var(--border); }}
  .no-shots {{ color: var(--text-tertiary); font-size: 14px; padding: 24px 0; }}

  /* ── Lightbox ── */
  .lb {{ display: none; position: fixed; inset: 0; z-index: 1000; background: rgba(4,5,6,0.96); flex-direction: column; align-items: center; justify-content: center; }}
  .lb.open {{ display: flex; }}
  .lb img {{ max-width: 92vw; max-height: calc(100vh - 72px); object-fit: contain; border-radius: 4px; }}
  .lb-bar {{ position: absolute; bottom: 0; left: 0; right: 0; display: flex; align-items: center; justify-content: center; gap: 20px; padding: 16px; background: rgba(8,9,10,0.9); border-top: 1px solid var(--border); }}
  .lb-label {{ font-size: 14px; font-weight: 500; color: var(--text-primary); min-width: 160px; text-align: center; }}
  .lb-counter {{ font-size: 13px; color: var(--text-tertiary); font-family: var(--mono); }}
  .lb-btn {{ background: var(--bg-raised); border: 1px solid var(--border-light); border-radius: 8px; color: var(--text-secondary); font-size: 18px; width: 44px; height: 44px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.12s; }}
  .lb-btn:hover {{ background: var(--bg-hover); color: var(--text-primary); border-color: var(--text-tertiary); }}
  .lb-btn:disabled {{ opacity: 0.15; cursor: default; pointer-events: none; }}
  .lb-close {{ position: absolute; top: 16px; right: 20px; background: none; border: none; color: var(--text-tertiary); font-size: 32px; cursor: pointer; transition: color 0.12s; }}
  .lb-close:hover {{ color: var(--text-primary); }}
</style>
</head>
<body>

<div class="header">
  <h1>Scout Verify{" — " + app_name if app_name else ""}</h1>
  <div class="pills">
    <span class="pill" style="color:#4ade80">{passed} passed</span>
    <span class="pill" style="color:#ef4444">{failed} failed</span>
    <span class="pill">{total_ms:,}ms</span>
    <span class="pill">{timestamp}</span>
  </div>
</div>

<div class="layout">
  <nav class="sidebar">{"".join(sidebar_items)}</nav>
  <main class="main">{"".join(panels)}</main>
</div>

<div class="lb" id="lb">
  <button class="lb-close" onclick="closeLb()">&times;</button>
  <img id="lb-img" src="">
  <div class="lb-bar">
    <button class="lb-btn" id="lb-prev" onclick="lbNav(-1)">&#8592;</button>
    <span class="lb-label" id="lb-label"></span>
    <span class="lb-counter" id="lb-counter"></span>
    <button class="lb-btn" id="lb-next" onclick="lbNav(1)">&#8594;</button>
  </div>
</div>

<script>
const shotCounts = [{js_shot_counts}];
const shotLabels = [{js_labels_array}];
let curScenario = 0, lbScenario = -1, lbIdx = -1;

function selectScenario(idx) {{
  curScenario = idx;
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', +el.dataset.idx === idx));
  document.querySelectorAll('.panel').forEach(el => el.classList.toggle('active', +el.dataset.idx === idx));
  document.querySelector('.main').scrollTop = 0;
}}

function getThumbImg(sIdx, imgIdx) {{
  const panel = document.querySelector(`.panel[data-idx="${{sIdx}}"]`);
  const thumbs = panel.querySelectorAll('.thumb img');
  return thumbs[imgIdx]?.src || '';
}}

function openLightbox(sIdx, imgIdx) {{
  lbScenario = sIdx;
  lbIdx = imgIdx;
  updateLb();
  document.getElementById('lb').classList.add('open');
}}

function closeLb() {{
  document.getElementById('lb').classList.remove('open');
  lbScenario = -1;
}}

function lbNav(dir) {{
  if (lbScenario < 0) return;
  const next = lbIdx + dir;
  if (next < 0 || next >= shotCounts[lbScenario]) return;
  lbIdx = next;
  updateLb();
}}

function updateLb() {{
  document.getElementById('lb-img').src = getThumbImg(lbScenario, lbIdx);
  document.getElementById('lb-label').textContent = shotLabels[lbScenario][lbIdx];
  document.getElementById('lb-counter').textContent = `${{lbIdx + 1}} / ${{shotCounts[lbScenario]}}`;
  document.getElementById('lb-prev').disabled = lbIdx === 0;
  document.getElementById('lb-next').disabled = lbIdx === shotCounts[lbScenario] - 1;
}}

document.addEventListener('keydown', e => {{
  const lbOpen = document.getElementById('lb').classList.contains('open');
  if (lbOpen) {{
    if (e.key === 'Escape') closeLb();
    else if (e.key === 'ArrowLeft') lbNav(-1);
    else if (e.key === 'ArrowRight') lbNav(1);
    return;
  }}
  if (e.key === 'ArrowDown' || e.key === 'j') {{ e.preventDefault(); selectScenario(Math.min(curScenario + 1, shotCounts.length - 1)); }}
  if (e.key === 'ArrowUp' || e.key === 'k') {{ e.preventDefault(); selectScenario(Math.max(curScenario - 1, 0)); }}
}});

if (shotCounts.length > 0) selectScenario(0);
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
