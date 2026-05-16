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
    # Paired rows + a "missing endpoint" row (target-only, baseline_record_id NULL).
    # All endpoints live in the same list now — missing endpoints are detected by
    # NULL record_id on one side.
    diffs = [
        {
            "method": "GET",
            "path": "/admin/orders",
            "status_match": 1,
            "baseline_record_id": 1,
            "target_record_id": 2,
            "baseline_status": 200,
            "target_status": 200,
            "structure_match": 1,
            "diff_summary": "",
        },
        {
            "method": "GET",
            "path": "/admin/users",
            "status_match": 0,
            "baseline_record_id": 3,
            "target_record_id": 4,
            "baseline_status": 200,
            "target_status": 500,
            "structure_match": 0,
            "diff_summary": "- $.name: string",
        },
        {
            "method": "POST",
            "path": "/admin/new",
            "status_match": 1,
            "baseline_record_id": None,
            "target_record_id": 5,
            "baseline_status": None,
            "target_status": 201,
            "structure_match": 1,
            "diff_summary": "",
        },
    ]
    summary = {
        "total_paired": 2,
        "status_mismatches": 1,
        "structure_mismatches": 1,
        "missing_endpoints": 1,
    }
    out = tmp_path / "report.html"
    generate_diff_html(meta, diffs, summary, out)

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
    generate_diff_html(
        meta,
        [],
        {
            "total_paired": 0,
            "status_mismatches": 0,
            "structure_mismatches": 0,
            "missing_endpoints": 0,
        },
        out,
    )
    assert out.exists()
    assert "<html" in out.read_text()
