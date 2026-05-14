"""Endpoint sequence alignment — pairs API records from two runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from scout.matcher.normalize import normalize_query, paths_match


@dataclass
class AlignedPair:
    """A paired endpoint comparison unit."""
    baseline: dict[str, Any] | None
    target: dict[str, Any] | None
    method: str
    path: str


def _exact_key(record: dict) -> tuple[str, str, str]:
    """Grouping key: (method, normalized_path, normalized_query).

    Path is normalized (trailing slash stripped). Query is canonicalized by
    sorting keys and replacing dynamic-looking values (UUIDs, prefixed IDs
    like ``apk_…``, long hex/digit strings) with ``*``. So:

      ?limit=10&offset=0&publishable_key_id=apk_AAA       ┐
      ?limit=10&offset=0&publishable_key_id=apk_BBB       ┘ same key

      ?limit=10&offset=0                          → different key (no key)
      ?limit=20&offset=0&publishable_key_id=apk_AAA  → different (limit=20)
      ?limit=10&offset=0&publishable_key_id=apk_AAA&extra=foo  → different
    """
    parsed = urlparse(record["url"])
    path = parsed.path.rstrip("/") or "/"
    query = normalize_query(parsed.query)
    return (record["method"], path, query)


def align_records(
    baseline: list[dict[str, Any]],
    target: list[dict[str, Any]],
) -> list[AlignedPair]:
    """Align two sequences of API records.

    Strategy:
      1. Group by (method, normalized_path, query_string) — query exact.
      2. For target records whose key has no exact baseline match, try fuzzy
         path match (paths_match) with the SAME query string. This handles
         dynamic ID segments in the path while keeping query distinctions.
      3. Within each group, pair by occurrence order (timestamp-sorted).

    Why query is part of the key: two requests to the same path with
    different query strings — e.g. ?limit=3&fields=… and ?limit=20&offset=0
    — are distinct logical calls (filter-search vs. paginated list). When
    parallel React-query refetches arrive in slightly different order between
    runs, sorting by full URL within a path-only group can pair URL_A with
    URL_B; using query as part of the group key prevents that.

    Unmatched baseline records → removed (target=None).
    Unmatched target records → added (baseline=None).
    """
    base_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    target_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    for rec in baseline:
        base_groups[_exact_key(rec)].append(rec)

    base_keys = list(base_groups.keys())

    def _resolve_key(rec: dict) -> tuple[str, str, str]:
        """Resolve a target record's key against baseline groups.

        Try exact match first. If absent, look for a baseline key with the
        same method + query string and a path that matches fuzzily (dynamic
        IDs allowed). Falls back to the record's own key if no match —
        the record then becomes a target-only "added" entry.
        """
        own = _exact_key(rec)
        if own in base_groups:
            return own
        own_method, own_path, own_query = own
        for bk in base_keys:
            b_method, b_path, b_query = bk
            if b_method == own_method and b_query == own_query and paths_match(b_path, own_path):
                return bk
        return own

    for rec in target:
        target_groups[_resolve_key(rec)].append(rec)

    all_keys = list(dict.fromkeys(list(base_groups.keys()) + list(target_groups.keys())))
    result: list[AlignedPair] = []

    for k in all_keys:
        method, path, _query = k
        b_list = sorted(base_groups.get(k, []), key=lambda r: r.get("timestamp") or "")
        t_list = sorted(target_groups.get(k, []), key=lambda r: r.get("timestamp") or "")

        pairs = min(len(b_list), len(t_list))
        for i in range(pairs):
            result.append(AlignedPair(baseline=b_list[i], target=t_list[i], method=method, path=path))
        for i in range(pairs, len(b_list)):
            result.append(AlignedPair(baseline=b_list[i], target=None, method=method, path=path))
        for i in range(pairs, len(t_list)):
            result.append(AlignedPair(baseline=None, target=t_list[i], method=method, path=path))

    return result
