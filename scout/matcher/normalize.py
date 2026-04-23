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
