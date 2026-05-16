"""Tests for report/junit.py — JUnit XML generation."""

import xml.etree.ElementTree as ET
from pathlib import Path

from scout.report.junit import generate_junit
from scout.runner.executor import ExecutionResult


def test_generate_junit_all_pass(tmp_path: Path) -> None:
    results = {
        "auth/login": ExecutionResult(success=True, duration_ms=500),
        "auth/logout": ExecutionResult(success=True, duration_ms=200),
    }
    out = tmp_path / "junit.xml"
    generate_junit(results, out, run_id="run-001")
    tree = ET.parse(out)  # noqa: S314  parsing our own generated output, not untrusted input
    suite = tree.getroot()
    assert suite.tag == "testsuite"
    assert suite.get("tests") == "2"
    assert suite.get("failures") == "0"
    assert len(suite.findall("testcase")) == 2


def test_generate_junit_with_failure(tmp_path: Path) -> None:
    results = {
        "auth/login": ExecutionResult(
            success=False, errors=["Element not found"], duration_ms=300
        ),
    }
    out = tmp_path / "junit.xml"
    generate_junit(results, out, run_id="run-001")
    tree = ET.parse(out)  # noqa: S314  parsing our own generated output, not untrusted input
    case = tree.getroot().find("testcase")
    failure = case.find("failure")
    assert failure is not None
    assert "Element not found" in (failure.text or "")
