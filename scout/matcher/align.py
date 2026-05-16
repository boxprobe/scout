"""Endpoint sequence alignment — pairs API records from two runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from scout.matcher.normalize import paths_match, query_key_set


@dataclass
class AlignedPair:
    """A paired endpoint comparison unit."""

    baseline: dict[str, Any] | None
    target: dict[str, Any] | None
    method: str
    path: str


def _path_key(record: dict) -> tuple[str, str]:
    """Grouping key: (method, normalized_path).

    Path is normalized (trailing slash stripped). Query string is NOT part
    of endpoint identity — different ``?…`` on the same path are different
    REQUESTS to the same API, not different APIs. The query difference is
    surfaced as a per-row annotation in the diff report instead of inflating
    the endpoint-change count.
    """
    parsed = urlparse(record["url"])
    path = parsed.path.rstrip("/") or "/"
    return (record["method"], path)


def align_records(
    baseline: list[dict[str, Any]],
    target: list[dict[str, Any]],
) -> list[AlignedPair]:
    """Align two sequences of API records.

    Strategy:
      1. Group by (method, normalized_path). Fuzzy path matching
         (:func:`paths_match`) bridges dynamic ID segments so e.g.
         ``/admin/orders/ord_A`` and ``/admin/orders/ord_B`` end up in the
         same group.
      2. Within each group, pair in two stages so the obvious matches don't
         get blocked by quirky scheduling:

           Stage 1 (exact query key set): records with identical query
             keys/value-elements get matched first by occurrence order.
             This handles the common case where baseline and target each
             fired the same N requests to the endpoint.

           Stage 2 (remaining by occurrence order): any leftover records
             on each side are paired in timestamp order. The two records in
             such a pair share a path but have differing query keys — they
             still represent the same logical endpoint call (the client
             asked the same endpoint for different field subsets), so the
             diff report surfaces the +/- query keys in a dedicated column
             rather than reporting them as separate endpoints.

    Unmatched baseline records → removed (target=None).
    Unmatched target records → added (baseline=None).
    """
    base_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    target_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for rec in baseline:
        base_groups[_path_key(rec)].append(rec)

    base_keys = list(base_groups.keys())

    def _resolve_path_key(rec: dict) -> tuple[str, str]:
        own = _path_key(rec)
        if own in base_groups:
            return own
        own_method, own_path = own
        for bk in base_keys:
            b_method, b_path = bk
            if b_method == own_method and paths_match(b_path, own_path):
                return bk
        return own

    for rec in target:
        target_groups[_resolve_path_key(rec)].append(rec)

    all_keys = list(dict.fromkeys(list(base_groups.keys()) + list(target_groups.keys())))
    result: list[AlignedPair] = []

    for k in all_keys:
        method, path = k
        b_list = sorted(base_groups.get(k, []), key=lambda r: r.get("timestamp") or "")
        t_list = sorted(target_groups.get(k, []), key=lambda r: r.get("timestamp") or "")

        # Stage 1: greedy match on identical query_key_set. Both sides walk
        # in timestamp order; the first compatible target record consumes a
        # baseline record.
        paired_b: set[int] = set()
        paired_t: set[int] = set()
        b_keys = [query_key_set(urlparse(r["url"]).query) for r in b_list]
        t_keys = [query_key_set(urlparse(r["url"]).query) for r in t_list]
        for i, bk in enumerate(b_keys):
            for j, tk in enumerate(t_keys):
                if j in paired_t:
                    continue
                if bk == tk:
                    result.append(
                        AlignedPair(
                            baseline=b_list[i],
                            target=t_list[j],
                            method=method,
                            path=path,
                        )
                    )
                    paired_b.add(i)
                    paired_t.add(j)
                    break

        # Stage 2: pair remaining records by occurrence order. These pairs
        # share a path but have query-key differences — they'll show up in
        # the report with a non-empty query_diff cell.
        leftover_b = [b_list[i] for i in range(len(b_list)) if i not in paired_b]
        leftover_t = [t_list[j] for j in range(len(t_list)) if j not in paired_t]
        n = min(len(leftover_b), len(leftover_t))
        for k_idx in range(n):
            result.append(
                AlignedPair(
                    baseline=leftover_b[k_idx],
                    target=leftover_t[k_idx],
                    method=method,
                    path=path,
                )
            )
        for k_idx in range(n, len(leftover_b)):
            result.append(
                AlignedPair(baseline=leftover_b[k_idx], target=None, method=method, path=path)
            )
        for k_idx in range(n, len(leftover_t)):
            result.append(
                AlignedPair(baseline=None, target=leftover_t[k_idx], method=method, path=path)
            )

    return result
