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
    fields: tuple[str, ...] = ()
    value_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiffIgnoreConfig:
    """Noise reduction config loaded from app.json diff_ignore section."""
    fields: tuple[str, ...] = ()
    value_types: tuple[str, ...] = ()
    overrides: tuple[tuple[str, IgnoreRule], ...] = ()

    def rule_for(self, method: str, path: str) -> IgnoreRule:
        """Return the merged rule for a specific endpoint.

        Overrides extend the global rule — they add fields/value_types on top.
        If an override field starts with '!', it removes from the global set.
        """
        g_fields = set(self.fields)
        g_types = set(self.value_types)

        for pattern, rule in self.overrides:
            if _endpoint_matches(pattern, method, path):
                for f in rule.fields:
                    if f.startswith("!"):
                        g_fields.discard(f[1:])
                    else:
                        g_fields.add(f)
                for t in rule.value_types:
                    if t.startswith("!"):
                        g_types.discard(t[1:])
                    else:
                        g_types.add(t)

        return IgnoreRule(fields=tuple(sorted(g_fields)), value_types=tuple(sorted(g_types)))


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
    """Parse diff_ignore section from app.json data.

    Expected format:
    {
        "fields": ["created_at", "updated_at", "*_token"],
        "value_types": ["uuid", "iso_timestamp", "mock_name", "mock_email"],
        "overrides": [
            {
                "pattern": "GET /admin/orders/*",
                "fields": ["!id"],
                "value_types": ["date"]
            }
        ]
    }
    """
    if not data:
        return DiffIgnoreConfig()

    fields = tuple(data.get("fields", []))
    value_types = tuple(data.get("value_types", []))

    overrides: list[tuple[str, IgnoreRule]] = []
    for ov in data.get("overrides", []):
        pattern = ov.get("pattern", "")
        if pattern:
            overrides.append((
                pattern,
                IgnoreRule(
                    fields=tuple(ov.get("fields", [])),
                    value_types=tuple(ov.get("value_types", [])),
                ),
            ))

    return DiffIgnoreConfig(
        fields=fields,
        value_types=value_types,
        overrides=tuple(overrides),
    )
