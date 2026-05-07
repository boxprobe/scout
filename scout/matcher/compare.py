"""API record comparison — status code + JSON structure diffing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from scout.matcher.noise import (
    DiffIgnoreConfig,
    IgnoreRule,
    filter_body,
    should_ignore_value_diff,
)


@dataclass
class EndpointDiff:
    """Result of comparing one endpoint between baseline and target."""
    status_match: bool
    baseline_status: int | None = None
    target_status: int | None = None
    structure_match: bool = True
    diff_summary: str = ""
    value_match: bool = True
    value_diff: str = ""


def _json_schema(obj: Any, path: str = "$") -> dict[str, str]:
    """Extract a flat {path: type_name} map from a JSON value.

    Arrays are represented by inspecting the first element.
    """
    schema: dict[str, str] = {}

    if isinstance(obj, dict):
        schema[path] = "object"
        for key, val in obj.items():
            schema.update(_json_schema(val, f"{path}.{key}"))
    elif isinstance(obj, list):
        schema[path] = "array"
        if obj:
            schema.update(_json_schema(obj[0], f"{path}[]"))
    elif isinstance(obj, bool):
        schema[path] = "boolean"
    elif isinstance(obj, int):
        schema[path] = "number"
    elif isinstance(obj, float):
        schema[path] = "number"
    elif obj is None:
        schema[path] = "null"
    else:
        schema[path] = "string"

    return schema


def _parse_body(body: str | None) -> Any | None:
    """Try to parse body as JSON, return None if not JSON."""
    if body is None:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return body  # return raw string for non-JSON


def _diff_schemas(base_schema: dict[str, str], target_schema: dict[str, str]) -> str:
    """Produce a human-readable diff summary between two schemas."""
    base_keys = set(base_schema.keys())
    target_keys = set(target_schema.keys())

    lines: list[str] = []
    added = target_keys - base_keys
    removed = base_keys - target_keys
    common = base_keys & target_keys

    for key in sorted(added):
        lines.append(f"+ {key}: {target_schema[key]}")
    for key in sorted(removed):
        lines.append(f"- {key}: {base_schema[key]}")
    for key in sorted(common):
        if base_schema[key] != target_schema[key]:
            lines.append(f"~ {key}: {base_schema[key]} → {target_schema[key]}")

    return "\n".join(lines)


def _flatten_values(obj: Any, path: str = "$") -> dict[str, Any]:
    """Extract a flat {path: leaf_value} map from a JSON value."""
    result: dict[str, Any] = {}

    if isinstance(obj, dict):
        for key, val in obj.items():
            result.update(_flatten_values(val, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            result.update(_flatten_values(val, f"{path}[{i}]"))
    else:
        result[path] = obj

    return result


def _diff_values(
    base_obj: Any,
    target_obj: Any,
    value_types: tuple[str, ...] = (),
) -> str:
    """Compare leaf values between two JSON objects. Return diff lines.

    If value_types is provided, value pairs where both sides match the same
    noise type are silently skipped.
    """
    b_vals = _flatten_values(base_obj)
    t_vals = _flatten_values(target_obj)

    lines: list[str] = []
    all_keys = sorted(set(b_vals.keys()) | set(t_vals.keys()))
    for key in all_keys:
        if key in b_vals and key in t_vals:
            if b_vals[key] != t_vals[key]:
                if should_ignore_value_diff(b_vals[key], t_vals[key], value_types):
                    continue
                lines.append(f"≠ {key}: {_val_repr(b_vals[key])} → {_val_repr(t_vals[key])}")
        elif key in t_vals:
            lines.append(f"+ {key}: {_val_repr(t_vals[key])}")
        else:
            lines.append(f"- {key}: {_val_repr(b_vals[key])}")

    return "\n".join(lines)


def _val_repr(v: Any) -> str:
    """Short representation of a value for diff output."""
    if v is None:
        return "null"
    if isinstance(v, str):
        if len(v) > 80:
            return json.dumps(v[:77] + "...", ensure_ascii=False)
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def compare_pair(
    baseline: dict,
    target: dict,
    ignore: IgnoreRule | None = None,
) -> EndpointDiff:
    """Compare a baseline and target API record.

    If *ignore* is provided, matching fields are stripped from both bodies
    before comparison, and value-type noise is suppressed in diff output.
    """
    b_status = baseline.get("status_code")
    t_status = target.get("status_code")
    status_match = b_status == t_status

    b_body = _parse_body(baseline.get("response_body"))
    t_body = _parse_body(target.get("response_body"))

    # Apply field-level filtering to parsed JSON bodies
    if ignore and ignore.fields:
        if isinstance(b_body, (dict, list)):
            b_body = filter_body(b_body, ignore)
        if isinstance(t_body, (dict, list)):
            t_body = filter_body(t_body, ignore)

    # Both None
    if b_body is None and t_body is None:
        return EndpointDiff(
            status_match=status_match,
            baseline_status=b_status,
            target_status=t_status,
            structure_match=True,
        )

    # One None
    if b_body is None or t_body is None:
        return EndpointDiff(
            status_match=status_match,
            baseline_status=b_status,
            target_status=t_status,
            structure_match=False,
            diff_summary="One side has no response body",
        )

    # Both non-JSON (raw strings)
    if isinstance(b_body, str) and isinstance(t_body, str):
        return EndpointDiff(
            status_match=status_match,
            baseline_status=b_status,
            target_status=t_status,
            structure_match=(b_body == t_body),
            diff_summary="" if b_body == t_body else "Non-JSON body differs",
        )

    # One JSON, one not
    if type(b_body) != type(t_body):
        return EndpointDiff(
            status_match=status_match,
            baseline_status=b_status,
            target_status=t_status,
            structure_match=False,
            diff_summary="Response type mismatch (JSON vs non-JSON)",
        )

    # Both JSON — compare structure
    b_schema = _json_schema(b_body)
    t_schema = _json_schema(t_body)
    structure_match = (b_schema == t_schema)
    diff_summary = "" if structure_match else _diff_schemas(b_schema, t_schema)

    # Compare values (with value-type noise suppression)
    vt = ignore.value_types if ignore else ()
    value_diff = _diff_values(b_body, t_body, value_types=vt)
    value_match = not bool(value_diff)

    return EndpointDiff(
        status_match=status_match,
        baseline_status=b_status,
        target_status=t_status,
        structure_match=structure_match,
        diff_summary=diff_summary,
        value_match=value_match,
        value_diff=value_diff,
    )
