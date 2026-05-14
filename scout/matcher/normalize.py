"""URL path normalization for endpoint matching."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    """Extract path from URL, strip query params and trailing slash."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return path or "/"


import re

_ID_RE = re.compile(
    r"""
    ^[0-9]+$                              # pure integer
    | ^[0-9a-f]{8}-[0-9a-f]{4}-          # UUID prefix
    | ^[a-z]+_[a-z0-9_]+$                # prefixed id: ord_ABC, item_1
    | .*[0-9]{4,}.*                       # contains 4+ consecutive digits
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _is_id_segment(seg: str) -> bool:
    """Return True if segment looks like a dynamic ID (not a fixed path word)."""
    return bool(_ID_RE.match(seg))


def paths_match(path_a: str, path_b: str) -> bool:
    """Check if two URL paths refer to the same endpoint.

    Allows segments to differ when both sides look like dynamic IDs or when
    strictly more than half of all segments match literally.
    """
    segs_a = path_a.strip("/").split("/")
    segs_b = path_b.strip("/").split("/")

    if len(segs_a) != len(segs_b):
        return False

    if not segs_a:
        return True

    literal_match = 0
    structural_conflict = False  # a segment pair where neither side is an ID and they differ

    for a, b in zip(segs_a, segs_b):
        if a == b:
            literal_match += 1
        elif _is_id_segment(a) or _is_id_segment(b):
            # differing ID-like segments are treated as wildcards — no conflict
            pass
        else:
            structural_conflict = True

    if structural_conflict:
        return False

    # All differing segments were ID-like; require at least one literal match
    # so that purely-ID paths (e.g. /123 vs /456) don't blindly match.
    return literal_match > 0 or len(segs_a) == 0


def _parse_qs(query: str) -> dict[str, str]:
    """Parse a query string into a {key: value} dict (last value wins on dupes).

    Intentionally NOT using urllib.parse.parse_qs — we want to preserve the
    raw encoded form so byte-for-byte comparison stays predictable, and we
    don't want list-valued keys here (downstream pairing extracts diffs
    string-by-string).
    """
    out: dict[str, str] = {}
    if not query:
        return out
    for kv in query.split("&"):
        if not kv:
            continue
        if "=" in kv:
            k, v = kv.split("=", 1)
        else:
            k, v = kv, ""
        out[k] = v
    return out


def query_key_set(query: str) -> tuple[str, ...]:
    """Sorted tuple of query parameter KEYS, ignoring values.

    Two URLs that share the same path and the same query key set are taken
    to be the same logical API call — differences in values (whether truly
    dynamic IDs or real param values) are reported as content diffs after
    pairing, not as separate endpoints. Adding or removing a query key is
    what constitutes a distinct API.
    """
    return tuple(sorted(_parse_qs(query).keys()))


def extract_query_dynamic_pairs(query_a: str, query_b: str) -> list[tuple[str, str]]:
    """Return (value_a, value_b) for each query key whose values differ.

    Caller is responsible for verifying that ``query_a`` and ``query_b``
    share the same key set (typically by way of alignment grouping on
    :func:`query_key_set`). Keys that exist on only one side are ignored —
    those alignment cases are already represented as one-sided endpoint
    records. Identical values are skipped.

    The returned list is suitable for feeding into the same path-derived
    dynamic-pair substitution used to normalize bodies before comparison
    (see ``cli._normalize_dynamic_ids``). This lets a logical-but-
    differently-keyed pair such as ``?q=test-1a64e3`` vs
    ``?q=test-726260`` compare cleanly without per-app regex tuning.
    """
    da = _parse_qs(query_a)
    db = _parse_qs(query_b)
    pairs: list[tuple[str, str]] = []
    for k in sorted(set(da.keys()) & set(db.keys())):
        if da[k] != db[k]:
            pairs.append((da[k], db[k]))
    return pairs


def extract_dynamic_pairs(path_a: str, path_b: str) -> list[tuple[str, str]]:
    """Return (baseline_seg, target_seg) for each diverging dynamic segment.

    Only meaningful when paths_match(path_a, path_b) is True. Caller is responsible
    for verifying that. Returns empty list if segment counts don't match.

    Each tuple corresponds to one position in the path where baseline and target
    differ AND at least one side looks like a dynamic ID. Order matches path order
    so the i-th tuple is the i-th dynamic segment.
    """
    segs_a = path_a.strip("/").split("/")
    segs_b = path_b.strip("/").split("/")
    if len(segs_a) != len(segs_b):
        return []
    pairs: list[tuple[str, str]] = []
    for a, b in zip(segs_a, segs_b):
        if a != b and (_is_id_segment(a) or _is_id_segment(b)):
            pairs.append((a, b))
    return pairs
