"""Diff noise reduction — filter out fields and values that differ between runs
but are not meaningful regressions (timestamps, IDs, mock-generated values)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any


@dataclass(frozen=True)
class IgnoreRule:
    """A single noise ignore rule."""
    fields: tuple[str, ...] = ()       # simple names, any depth
    paths: tuple[str, ...] = ()        # $.path.expressions with [*]
    value_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatusOnlyRule:
    """Match (scenario, path, step_seq) — only compare status_code."""
    scenario: str    # glob pattern, "*" matches all
    path: str        # glob pattern for API path
    step_seq: str    # "*" | "3" | "1-5" range


@dataclass(frozen=True)
class DiffIgnoreConfig:
    """Noise reduction config loaded from diff_ignore.json."""
    fields: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    value_types: tuple[str, ...] = ()
    overrides: tuple[tuple[str, IgnoreRule], ...] = ()
    status_only: tuple[StatusOnlyRule, ...] = ()

    def is_status_only(self, scenario: str, path: str, step_seq: int | None) -> bool:
        """Return True if this (scenario, path, step_seq) should only compare status_code."""
        for rule in self.status_only:
            if not fnmatch(scenario, rule.scenario):
                continue
            if not fnmatch(path, rule.path):
                continue
            if not _step_seq_matches(rule.step_seq, step_seq):
                continue
            return True
        return False

    def rule_for(self, method: str, path: str) -> IgnoreRule:
        """Return the merged rule for a specific endpoint.

        Overrides extend the global rule — they add fields/value_types on top.
        If an override field starts with '!', it removes from the global set.
        """
        g_fields = set(self.fields)
        g_paths = set(self.paths)
        g_types = set(self.value_types)

        for pattern, rule in self.overrides:
            if _endpoint_matches(pattern, method, path):
                for f in rule.fields:
                    if f.startswith("!"):
                        g_fields.discard(f[1:])
                    else:
                        g_fields.add(f)
                for p in rule.paths:
                    if p.startswith("!"):
                        g_paths.discard(p[1:])
                    else:
                        g_paths.add(p)
                for t in rule.value_types:
                    if t.startswith("!"):
                        g_types.discard(t[1:])
                    else:
                        g_types.add(t)

        return IgnoreRule(
            fields=tuple(sorted(g_fields)),
            paths=tuple(sorted(g_paths)),
            value_types=tuple(sorted(g_types)),
        )


def _step_seq_matches(pattern: str, seq: int | None) -> bool:
    """Check if step_seq matches a pattern.

    Patterns:
      "*"   — matches any (including None)
      "3"   — matches exact seq
      "1-5" — matches range (inclusive)
    """
    if pattern == "*":
        return True
    if seq is None:
        return False
    if "-" in pattern:
        parts = pattern.split("-", 1)
        try:
            lo, hi = int(parts[0]), int(parts[1])
            return lo <= seq <= hi
        except ValueError:
            return False
    try:
        return seq == int(pattern)
    except ValueError:
        return False


def _endpoint_matches(pattern: str, method: str, path: str) -> bool:
    """Check if 'METHOD /path/pattern' matches.

    Pattern format: 'GET /admin/orders/*' or '* /admin/products/*'
    """
    parts = pattern.split(None, 1)
    if len(parts) != 2:
        return False
    p_method, p_path = parts
    if p_method != "*" and p_method.upper() != method.upper():
        return False
    return fnmatch(path, p_path)


# -- Path expression matching --


def _path_expr_to_regex(expr: str) -> re.Pattern[str]:
    """Convert a path expression like $.orders[*].created_at to a regex.

    [*] matches any array index [0], [1], etc.
    """
    # Escape dots and brackets, then replace [*] with [\d+]
    pattern = re.escape(expr)
    pattern = pattern.replace(r"\[\*\]", r"\[\d+\]")
    return re.compile("^" + pattern + "$")


def path_ignored(diff_path: str, path_exprs: tuple[str, ...]) -> bool:
    """Check if a diff output path matches any path expression."""
    for expr in path_exprs:
        regex = _path_expr_to_regex(expr)
        if regex.match(diff_path):
            return True
    return False


def filter_diff_lines(diff_text: str, path_exprs: tuple[str, ...]) -> str:
    """Remove diff lines whose path matches any path expression.

    Diff lines look like: '≠ $.data.field: old → new'
    """
    if not path_exprs or not diff_text:
        return diff_text
    lines = []
    for line in diff_text.split("\n"):
        p = _extract_diff_path(line)
        if p and path_ignored(p, path_exprs):
            continue
        lines.append(line)
    return "\n".join(lines)


_DIFF_PATH_RE = re.compile(r"^[≠+\-~]\s+(\$\S+?):")


def _extract_diff_path(line: str) -> str | None:
    """Extract the path from a diff line like '≠ $.data.field: ...'."""
    m = _DIFF_PATH_RE.match(line)
    return m.group(1) if m else None


# -- Value type detectors --

from scout.mock_vars import MOCK_DETECTORS as _MOCK_DETECTORS

# Built-in type detectors (non-mock patterns)
_BUILTIN_DETECTORS: dict[str, re.Pattern[str]] = {
    "uuid": re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    ),
    "iso_timestamp": re.compile(
        r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    ),
    "unix_timestamp": re.compile(
        r"^1[6-9]\d{8}$"  # 2020-2033 range in seconds
    ),
    "date": re.compile(
        r"^\d{4}-\d{2}-\d{2}$"
    ),
    "hex_token": re.compile(
        r"^[a-z]{2,}_[0-9a-f]{40,}$"
    ),
    "prefixed_id": re.compile(
        r"^[a-z]{2,}_{1}[0-9A-Za-z]{20,}$"
    ),
}

# Merge: built-in + mock detectors from mock_vars registry
_DETECTORS: dict[str, re.Pattern[str]] = {**_BUILTIN_DETECTORS, **_MOCK_DETECTORS}


def detect_value_type(value: Any) -> str | None:
    """Detect if a value matches a known noise pattern. Returns type name or None."""
    if not isinstance(value, str):
        if isinstance(value, (int, float)):
            s = str(int(value)) if isinstance(value, float) and value == int(value) else str(value)
            if _DETECTORS["unix_timestamp"].match(s):
                return "unix_timestamp"
        return None

    for name, pattern in _DETECTORS.items():
        if pattern.match(value):
            return name
    return None


def filter_body(obj: Any, rule: IgnoreRule) -> Any:
    """Recursively remove ignored fields from a parsed JSON body.

    Returns a new object with ignored fields stripped.
    Only handles simple field names (not path expressions).
    """
    if not rule.fields:
        return obj
    if isinstance(obj, dict):
        return {
            k: filter_body(v, rule)
            for k, v in obj.items()
            if not _field_ignored(k, rule.fields)
        }
    if isinstance(obj, list):
        return [filter_body(item, rule) for item in obj]
    return obj


def _field_ignored(key: str, patterns: tuple[str, ...]) -> bool:
    """Check if a field name matches any ignore pattern."""
    for p in patterns:
        if p == key:
            return True
        if fnmatch(key, p):
            return True
    return False


def should_ignore_value_diff(
    base_val: Any,
    target_val: Any,
    value_types: tuple[str, ...],
) -> bool:
    """Return True if both values match the same noise type and that type is ignored."""
    if not value_types:
        return False
    b_type = detect_value_type(base_val)
    t_type = detect_value_type(target_val)
    if b_type is None or t_type is None:
        return False
    if b_type != t_type:
        return False
    return b_type in value_types


def load_diff_ignore(data: dict[str, Any] | None) -> DiffIgnoreConfig:
    """Parse diff_ignore.json data.

    Expected format:
    {
        "fields": ["created_at", "updated_at", "$.orders[*].metadata"],
        "value_types": ["uuid", "iso_timestamp"],
        "status_only": [
            {"path": "/admin/notifications", "scenario": "*", "step_seq": "*"}
        ],
        "overrides": [
            {
                "pattern": "GET /admin/orders/*",
                "fields": ["!id"],
                "value_types": ["date"]
            }
        ]
    }

    Fields starting with '$' are treated as path expressions.
    """
    if not data:
        return DiffIgnoreConfig()

    raw_fields = data.get("fields", [])
    # Separate simple names from path expressions
    simple_fields: list[str] = []
    path_exprs: list[str] = []
    for f in raw_fields:
        if f.startswith("$"):
            path_exprs.append(f)
        else:
            simple_fields.append(f)

    value_types = tuple(data.get("value_types", []))

    overrides: list[tuple[str, IgnoreRule]] = []
    for ov in data.get("overrides", []):
        pattern = ov.get("pattern", "")
        if pattern:
            ov_fields: list[str] = []
            ov_paths: list[str] = []
            for f in ov.get("fields", []):
                if f.startswith("$") or (f.startswith("!") and f[1:].startswith("$")):
                    ov_paths.append(f)
                else:
                    ov_fields.append(f)
            overrides.append((
                pattern,
                IgnoreRule(
                    fields=tuple(ov_fields),
                    paths=tuple(ov_paths),
                    value_types=tuple(ov.get("value_types", [])),
                ),
            ))

    status_only: list[StatusOnlyRule] = []
    for so in data.get("status_only", []):
        status_only.append(StatusOnlyRule(
            scenario=so.get("scenario", "*"),
            path=so.get("path", "*"),
            step_seq=str(so.get("step_seq", "*")),
        ))

    return DiffIgnoreConfig(
        fields=tuple(simple_fields),
        paths=tuple(path_exprs),
        value_types=value_types,
        overrides=tuple(overrides),
        status_only=tuple(status_only),
    )
