"""Endpoint sequence alignment — pairs API records from two runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scout.matcher.normalize import normalize_url, paths_match


@dataclass
class AlignedPair:
    """A paired endpoint comparison unit."""
    baseline: dict[str, Any] | None
    target: dict[str, Any] | None
    method: str
    path: str


def _key(record: dict) -> tuple[str, str]:
    """Extract (method, normalized_path) from a record."""
    return (record["method"], normalize_url(record["url"]))


def _match(a: dict, b: dict) -> bool:
    """Check if two records refer to the same endpoint."""
    if a["method"] != b["method"]:
        return False
    return paths_match(normalize_url(a["url"]), normalize_url(b["url"]))


def _group_key(record: dict) -> tuple[str, str]:
    """Grouping key: (method, normalized_path) using paths_match for fuzzy grouping."""
    return _key(record)


def align_records(
    baseline: list[dict[str, Any]],
    target: list[dict[str, Any]],
) -> list[AlignedPair]:
    """Align two sequences of API records.

    Strategy: group by (method, normalized_path), pair within each group
    by occurrence order. This handles reordered async API responses correctly.
    Unmatched baseline records → removed (target=None).
    Unmatched target records → added (baseline=None).
    """
    from collections import defaultdict

    # Group records by (method, path), preserving order within each group
    base_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    target_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    # For fuzzy matching, we need to resolve target keys against baseline keys
    base_key_map: dict[tuple[str, str], tuple[str, str]] = {}

    for rec in baseline:
        k = _key(rec)
        base_groups[k].append(rec)
        base_key_map[k] = k

    def _resolve_key(rec: dict) -> tuple[str, str]:
        """Find matching baseline key using paths_match, or use own key."""
        k = _key(rec)
        if k in base_key_map:
            return k
        # Try fuzzy match against known baseline keys
        method, path = k
        for bk in base_key_map:
            if bk[0] == method and paths_match(bk[1], path):
                return bk
        return k

    for rec in target:
        k = _resolve_key(rec)
        target_groups[k].append(rec)

    # Pair within each group by URL similarity (sort by full URL so similar URLs align)
    all_keys = list(dict.fromkeys(list(base_groups.keys()) + list(target_groups.keys())))
    result: list[AlignedPair] = []

    for k in all_keys:
        b_list = sorted(base_groups.get(k, []), key=lambda r: r["url"])
        t_list = sorted(target_groups.get(k, []), key=lambda r: r["url"])
        method, path = k

        pairs = min(len(b_list), len(t_list))
        for i in range(pairs):
            result.append(AlignedPair(baseline=b_list[i], target=t_list[i], method=method, path=path))
        for i in range(pairs, len(b_list)):
            result.append(AlignedPair(baseline=b_list[i], target=None, method=method, path=path))
        for i in range(pairs, len(t_list)):
            result.append(AlignedPair(baseline=None, target=t_list[i], method=method, path=path))

    return result
