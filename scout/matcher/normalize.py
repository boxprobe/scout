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


_DYN_VALUE_RE = re.compile(
    r"""
    ^[0-9a-f]{8}-[0-9a-f]{4}-       # UUID (full or prefix)
    | ^[a-z]+_[a-zA-Z0-9_-]{8,}$    # prefixed id: apk_01KRJQZKQ..., region_03ABCDEFGH
    | ^[a-fA-F0-9]{16,}$             # long hex string (token, hash digest)
    | ^[0-9]{8,}$                    # 8+ digit number (timestamp, big id)
    """,
    re.VERBOSE,
)


def _looks_like_dynamic_value(value: str) -> bool:
    """Return True if a query string value looks like a per-run-unique ID.

    Intentionally NARROWER than _is_id_segment used for path matching:
    short integers (limit=10) and short alphanumerics (type=publishable)
    are real parameters whose values must match exactly across runs.
    """
    if not value or len(value) < 4:
        return False
    return bool(_DYN_VALUE_RE.search(value))


def normalize_query(query: str) -> str:
    """Canonicalize a query string for endpoint alignment.

    Sorts keys for stable ordering and replaces each dynamic-looking value
    with ``*`` so URLs that differ only in run-unique IDs end up in the
    same alignment group. Two URLs with structurally identical keys and
    the same non-dynamic values normalize to the same string.
    """
    if not query:
        return ""
    pairs: list[tuple[str, str]] = []
    for kv in query.split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
        else:
            k, v = kv, ""
        if _looks_like_dynamic_value(v):
            v = "*"
        pairs.append((k, v))
    pairs.sort()
    return "&".join(f"{k}={v}" for k, v in pairs)


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
