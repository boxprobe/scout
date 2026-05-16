"""API record comparison — status code + JSON structure diffing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from scout.matcher.noise import (
    IgnoreRule,
    KnownChange,
    filter_body,
    filter_diff_lines,
    filter_known_changes,
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
    header_match: bool = True
    header_diff: str = ""


# Headers that are expected to differ between runs / environments and carry
# no test-signal value. Kept lowercase since HTTP header names are case-insensitive.
DEFAULT_HEADER_IGNORE: frozenset[str] = frozenset(
    {
        "date",
        "etag",
        "if-none-match",
        "last-modified",
        "x-request-id",
        "x-trace-id",
        "x-correlation-id",
        "x-runtime",
        "server",
        "x-powered-by",
        "set-cookie",
        "cookie",
        "content-length",  # auto-derived from body
        "host",  # always differs between environments
    }
)


def _parse_headers(raw: str | None) -> dict[str, str]:
    """Parse headers from JSON-encoded TEXT (as recorded by the proxy).
    Lowercases keys for case-insensitive comparison. Returns {} on bad input.
    """
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in obj.items()}


def diff_response_headers(
    baseline_raw: str | None,
    target_raw: str | None,
    ignore: frozenset[str] | set[str] = DEFAULT_HEADER_IGNORE,
    extra_ignore: tuple[str, ...] = (),
) -> str:
    """Produce a unified-style diff text for response headers.

    Output format mirrors diff_summary / value_diff:
      + name: value      (target only)
      - name: value      (baseline only)
      ~ name: a -> b     (changed)
    Empty string when nothing meaningful differs.
    """
    b = _parse_headers(baseline_raw)
    t = _parse_headers(target_raw)
    if not b and not t:
        return ""
    # Merge built-in defaults with any user-supplied extra ignores from diff_ignore.json.
    # extra_ignore is already lowercased by the loader; defensive .lower() costs nothing.
    effective_ignore = set(ignore) | {h.lower() for h in extra_ignore}
    keys = (set(b) | set(t)) - effective_ignore
    lines: list[str] = []
    for name in sorted(keys):
        b_val = b.get(name)
        t_val = t.get(name)
        if b_val == t_val:
            continue
        if b_val is None:
            lines.append(f"+ {name}: {t_val}")
        elif t_val is None:
            lines.append(f"- {name}: {b_val}")
        else:
            lines.append(f"~ {name}: {b_val} -> {t_val}")
    return "\n".join(lines)


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
    known_changes: tuple[KnownChange, ...] = (),
    target_version: str = "",
    api_path: str = "",
    header_ignore: tuple[str, ...] = (),
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
    if type(b_body) is not type(t_body):
        return EndpointDiff(
            status_match=status_match,
            baseline_status=b_status,
            target_status=t_status,
            structure_match=False,
            diff_summary="Response type mismatch (JSON vs non-JSON)",
        )

    # Both JSON — compare structure. structure_match is derived from the
    # post-_diff_schemas output rather than raw schema equality, because
    # _diff_schemas applies its own suppression (e.g. empty-array tolerance)
    # and the boolean should agree with what the user sees.
    b_schema = _json_schema(b_body)
    t_schema = _json_schema(t_body)
    diff_summary = _diff_schemas(b_schema, t_schema)
    structure_match = not bool(diff_summary.strip())

    # Post-filter structure diff by path expressions. Path-based ignores are
    # project-wide noise rules — we drop them destructively from diff_summary
    # so they never reach the report.
    if ignore and ignore.paths and diff_summary:
        diff_summary = filter_diff_lines(diff_summary, ignore.paths)
        structure_match = not bool(diff_summary.strip())

    # Known version changes are filtered NON-destructively: structure_match
    # reflects the post-filter view (so a fully-covered row counts as a
    # match), but the raw diff_summary is preserved so the report can
    # render the affected paths and mark them as KNOWN.
    method = baseline.get("method", "") or target.get("method", "")
    if known_changes and target_version and diff_summary:
        filtered_for_known = filter_known_changes(
            diff_summary,
            known_changes,
            target_version,
            method=method,
            api_path=api_path,
        )
        structure_match = not bool(filtered_for_known.strip())

    # Compare values (with value-type noise suppression)
    vt = ignore.value_types if ignore else ()
    value_diff = _diff_values(b_body, t_body, value_types=vt)

    # Post-filter: remove diff lines matching path expressions
    if ignore and ignore.paths and value_diff:
        value_diff = filter_diff_lines(value_diff, ignore.paths)

    if known_changes and target_version and value_diff:
        value_diff = filter_known_changes(
            value_diff,
            known_changes,
            target_version,
            method=method,
            api_path=api_path,
        )

    value_match = not bool(value_diff)

    # Response header diff (request headers usually differ noisily — auth tokens,
    # session-bound identifiers — and have low signal value, so skip).
    header_diff = diff_response_headers(
        baseline.get("response_headers"),
        target.get("response_headers"),
        extra_ignore=header_ignore,
    )
    header_match = not bool(header_diff)

    return EndpointDiff(
        status_match=status_match,
        baseline_status=b_status,
        target_status=t_status,
        structure_match=structure_match,
        diff_summary=diff_summary,
        value_match=value_match,
        value_diff=value_diff,
        header_match=header_match,
        header_diff=header_diff,
    )
