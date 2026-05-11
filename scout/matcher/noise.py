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
    """Match (scenario, method, path, step_seq) — only compare status_code."""
    scenario: str    # glob pattern, "*" matches all
    method: str      # HTTP method glob, "*" matches all
    path: str        # glob pattern for API path
    step_seq: str    # "*" | "3" | "1-5" range


@dataclass(frozen=True)
class KnownChange:
    """A known structural change tied to a version."""
    endpoint: str      # "METHOD /path/pattern", e.g. "POST /admin/product-categories/*"
    path: str          # $.field.path expression
    change: str        # "added" | "removed"
    since: str         # semver string, e.g. "2.14.0"
    note: str = ""


@dataclass(frozen=True)
class DiffIgnoreConfig:
    """Noise reduction config loaded from diff_ignore.json."""
    fields: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    value_types: tuple[str, ...] = ()
    overrides: tuple[tuple[str, IgnoreRule], ...] = ()
    status_only: tuple[StatusOnlyRule, ...] = ()
    known_changes: tuple[KnownChange, ...] = ()
    # Extra response-header names to ignore on top of DEFAULT_HEADER_IGNORE
    # (compare.py). Lowercased on load for case-insensitive matching.
    header_ignore: tuple[str, ...] = ()

    def is_status_only(
        self, scenario: str, method: str, path: str, step_seq: int | None,
    ) -> bool:
        """Return True if (scenario, method, path, step_seq) should only compare status_code."""
        for rule in self.status_only:
            if not fnmatch(scenario, rule.scenario):
                continue
            if not fnmatch(method.upper(), rule.method.upper()):
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


# -- Version-aware known changes --


def _parse_semver(v: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of ints for comparison."""
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            # Strip non-numeric suffix (e.g. "14-beta" → 14)
            m = re.match(r"(\d+)", p)
            parts.append(int(m.group(1)) if m else 0)
    return tuple(parts)


def _version_gte(version: str, since: str) -> bool:
    """Return True if version >= since using semver comparison."""
    return _parse_semver(version) >= _parse_semver(since)


def filter_known_changes(
    diff_text: str,
    known_changes: tuple[KnownChange, ...],
    target_version: str,
    method: str = "",
    api_path: str = "",
) -> str:
    """Remove structure diff lines that match known version changes.

    A '+ path: type' line is suppressed if a known_change with change='added'
    exists for that path, the endpoint matches, and target_version >= since.

    A '- path: type' line is suppressed if change='removed' and same conditions.
    """
    if not known_changes or not target_version or not diff_text:
        return diff_text

    added_paths: set[str] = set()
    removed_paths: set[str] = set()
    for kc in known_changes:
        if not _version_gte(target_version, kc.since):
            continue
        if kc.endpoint and method and api_path:
            if not _endpoint_matches(kc.endpoint, method, api_path):
                continue
        if kc.change == "added":
            added_paths.add(kc.path)
        elif kc.change == "removed":
            removed_paths.add(kc.path)

    if not added_paths and not removed_paths:
        return diff_text

    lines = []
    for line in diff_text.split("\n"):
        p = _extract_diff_path(line)
        if p:
            if line.startswith("+ ") and _known_path_matches(p, added_paths):
                continue
            if line.startswith("- ") and _known_path_matches(p, removed_paths):
                continue
        lines.append(line)
    return "\n".join(lines)


def _known_path_matches(diff_path: str, known_paths: set[str]) -> bool:
    """Check if a diff path matches any known change path (with [*] support)."""
    for kp in known_paths:
        if kp == diff_path:
            return True
        regex = _path_expr_to_regex(kp)
        if regex.match(diff_path):
            return True
    return False


# -- Path expression matching --


def _path_expr_to_regex(expr: str) -> re.Pattern[str]:
    """Convert a path expression like $.orders[*].created_at to a regex.

    Both [*] (xpath-style) and [] (jsonpath-style) match any array index.
    """
    # Escape dots and brackets, then replace wildcards with \d+
    pattern = re.escape(expr)
    pattern = pattern.replace(r"\[\*\]", r"\[\d+\]")
    pattern = pattern.replace(r"\[\]", r"\[\d+\]")
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

    from scout.matcher.normalize import _is_id_segment

    def _split_endpoint(endpoint: str) -> tuple[str, str]:
        """Split 'METHOD /path' into (method, path). Lone path → ('*', path)."""
        s = endpoint.strip()
        if " " in s:
            method, _, path = s.partition(" ")
            return method.strip() or "*", path.strip() or "*"
        return "*", s or "*"

    status_only: list[StatusOnlyRule] = []
    for so in data.get("status_only", []):
        # Prefer the new `endpoint` form ("METHOD /path") that mirrors known_changes.
        # Legacy: fall back to `path` (with implicit method="*") for backward compat.
        if "endpoint" in so:
            raw_method, raw_path = _split_endpoint(so["endpoint"])
        else:
            raw_method = "*"
            raw_path = so.get("path", "*")
        # Auto-templatize concrete ID segments in the path part
        if raw_path != "*" and "*" not in raw_path:
            segments = raw_path.split("/")
            raw_path = "/".join("*" if s and _is_id_segment(s) else s for s in segments)
        status_only.append(StatusOnlyRule(
            scenario=so.get("scenario", "*"),
            method=raw_method,
            path=raw_path,
            step_seq=str(so.get("step_seq", "*")),
        ))

    known_changes: list[KnownChange] = []
    for kc in data.get("known_changes", []):
        change = kc.get("change", "")
        if change in ("added", "removed") and kc.get("path") and kc.get("since"):
            known_changes.append(KnownChange(
                endpoint=kc.get("endpoint", "*"),
                path=kc["path"],
                change=change,
                since=kc["since"],
                note=kc.get("note", ""),
            ))

    # Response-header ignore list (extends DEFAULT_HEADER_IGNORE in compare.py).
    # Lowercase here so comparison can be case-insensitive without per-call work.
    header_ignore = tuple(
        str(h).lower() for h in data.get("header_ignore", []) if h
    )

    return DiffIgnoreConfig(
        fields=tuple(simple_fields),
        paths=tuple(path_exprs),
        value_types=value_types,
        overrides=tuple(overrides),
        status_only=tuple(status_only),
        known_changes=tuple(known_changes),
        header_ignore=header_ignore,
    )
