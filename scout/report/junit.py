"""JUnit XML report generation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scout.runner.executor import ExecutionResult


def generate_junit(
    results: dict[str, ExecutionResult],
    output_path: Path,
    *,
    run_id: str = "",
) -> None:
    failures = sum(1 for r in results.values() if not r.success)
    total_time = sum(r.duration_ms for r in results.values()) / 1000

    suite = ET.Element(
        "testsuite",
        {
            "name": f"scout-{run_id}" if run_id else "scout",
            "tests": str(len(results)),
            "failures": str(failures),
            "time": f"{total_time:.3f}",
        },
    )

    for scenario_path, result in results.items():
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "name": scenario_path,
                "classname": scenario_path.replace("/", "."),
                "time": f"{result.duration_ms / 1000:.3f}",
            },
        )
        if not result.success:
            failure = ET.SubElement(
                case,
                "failure",
                {
                    "message": result.errors[0] if result.errors else "Unknown error",
                },
            )
            failure.text = "\n".join(result.errors)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="unicode", xml_declaration=True)
