"""Tests for report/html.py — HTML report generation."""

from pathlib import Path

from scout.report.html import generate_html
from scout.runner.executor import ExecutionResult


def test_generate_html_report(tmp_path: Path) -> None:
    results = {
        "auth/login": ExecutionResult(success=True, duration_ms=500),
        "auth/logout": ExecutionResult(success=False, errors=["timeout"], duration_ms=3000),
    }
    out = tmp_path / "report.html"
    generate_html(results, out, run_id="run-001", app_name="medusa-admin")
    html = out.read_text()
    assert "auth/login" in html
    assert "auth/logout" in html
    assert "PASSED" in html
    assert "FAILED" in html
    assert "medusa-admin" in html


def test_generate_html_empty(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_html({}, out, run_id="run-001")
    assert out.exists()
    assert "<html" in out.read_text()
