"""Tests for matcher/align.py — endpoint sequence alignment."""

from scout.matcher.align import align_records, AlignedPair


def _rec(method: str, url: str, status: int = 200) -> dict:
    """Minimal record dict for testing."""
    return {"method": method, "url": url, "status_code": status, "response_body": None}


def test_identical_sequences() -> None:
    """Same endpoints in same order → all paired."""
    base = [_rec("GET", "http://h/admin/orders"), _rec("GET", "http://h/admin/users")]
    target = [_rec("GET", "http://h/admin/orders"), _rec("GET", "http://h/admin/users")]
    result = align_records(base, target)
    assert len(result) == 2
    assert all(p.baseline is not None and p.target is not None for p in result)


def test_extra_in_target() -> None:
    """Target has an extra endpoint → marked as added."""
    base = [_rec("GET", "http://h/a")]
    target = [_rec("GET", "http://h/a"), _rec("GET", "http://h/b")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    added = [p for p in result if p.baseline is None]
    assert len(paired) == 1
    assert len(added) == 1


def test_missing_in_target() -> None:
    """Baseline has an endpoint target doesn't → marked as removed."""
    base = [_rec("GET", "http://h/a"), _rec("GET", "http://h/b")]
    target = [_rec("GET", "http://h/a")]
    result = align_records(base, target)
    removed = [p for p in result if p.target is None]
    assert len(removed) == 1


def test_id_segment_alignment() -> None:
    """Endpoints with different IDs in path still align."""
    base = [_rec("GET", "http://h/orders/ord_A")]
    target = [_rec("GET", "http://h/orders/ord_B")]
    result = align_records(base, target)
    assert len(result) == 1
    assert result[0].baseline is not None and result[0].target is not None


def test_different_methods_no_match() -> None:
    """Same path but different HTTP methods do not pair."""
    base = [_rec("GET", "http://h/a")]
    target = [_rec("POST", "http://h/a")]
    result = align_records(base, target)
    removed = [p for p in result if p.target is None]
    added = [p for p in result if p.baseline is None]
    assert len(removed) == 1
    assert len(added) == 1


def test_empty_sequences() -> None:
    result = align_records([], [])
    assert result == []
