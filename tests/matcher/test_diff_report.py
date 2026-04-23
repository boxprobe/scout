"""Tests for matcher/diff_report.py — diff HTML report."""

from pathlib import Path

from scout.matcher.diff_report import generate_diff_html


def test_generate_diff_html(tmp_path: Path) -> None:
    meta = {
        "baseline_run_id": "20260423-a",
        "target_run_id": "20260423-b",
        "app": "medusa-admin",
        "scenario": "auth/login",
    }
    diffs = [
        {"method": "GET", "path": "/admin/orders", "status_match": 1,
         "baseline_status": 200, "target_status": 200,
         "structure_match": 1, "diff_summary": ""},
        {"method": "GET", "path": "/admin/users", "status_match": 0,
         "baseline_status": 200, "target_status": 500,
         "structure_match": 0, "diff_summary": "- $.name: string"},
    ]
    missing = [
        {"side": "target", "method": "POST", "path": "/admin/new", "status_code": 201},
    ]
    summary = {
        "total_paired": 2,
        "status_mismatches": 1,
        "structure_mismatches": 1,
        "missing_endpoints": 1,
    }
    out = tmp_path / "report.html"
    generate_diff_html(meta, diffs, missing, summary, out)

    html = out.read_text()
    assert "medusa-admin" in html
    assert "20260423-a" in html
    assert "/admin/orders" in html
    assert "/admin/users" in html
    assert "500" in html
    assert "/admin/new" in html


def test_generate_diff_html_no_issues(tmp_path: Path) -> None:
    meta = {"baseline_run_id": "a", "target_run_id": "b", "app": "x", "scenario": "s"}
    out = tmp_path / "report.html"
    generate_diff_html(meta, [], [], {"total_paired": 0, "status_mismatches": 0, "structure_mismatches": 0, "missing_endpoints": 0}, out)
    assert out.exists()
    assert "<html" in out.read_text()
