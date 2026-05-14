"""Tests for matcher/align.py — endpoint sequence alignment."""

from scout.matcher.align import align_records, AlignedPair


def _rec(method: str, url: str, status: int = 200, timestamp: str = "") -> dict:
    """Minimal record dict for testing."""
    return {"method": method, "url": url, "status_code": status, "response_body": None, "timestamp": timestamp}


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


def test_same_path_different_query_not_paired() -> None:
    """Same path with structurally different query strings must not pair.

    Regression for the alignment bug where, after parallel React-query
    refetches arrived in different order between runs, the path-only group
    key + URL-string sort would pair ?limit=3&… (a filter-search call) with
    ?limit=20&offset=0&… (a paginated list call). They are distinct logical
    calls and should each pair only with the same query on the other side.
    """
    base = [
        _rec("GET", "http://h/admin/api-keys?q=&limit=3&fields=id"),
        _rec("GET", "http://h/admin/api-keys?limit=20&offset=0&type=publishable"),
    ]
    target = [
        # Target's two parallel refetches arrive in the opposite order
        _rec("GET", "http://h/admin/api-keys?limit=20&offset=0&type=publishable"),
        _rec("GET", "http://h/admin/api-keys?q=&limit=3&fields=id"),
    ]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 2
    for p in paired:
        # Same query string on both sides of every pair
        assert p.baseline["url"] == p.target["url"]


def test_same_path_query_only_on_one_side() -> None:
    """Different query strings → no pair: one becomes removed, the other added."""
    base = [_rec("GET", "http://h/admin/api-keys?q=&limit=3")]
    target = [_rec("GET", "http://h/admin/api-keys?limit=20&offset=0")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    removed = [p for p in result if p.target is None]
    added = [p for p in result if p.baseline is None]
    assert paired == []
    assert len(removed) == 1
    assert len(added) == 1


def test_same_query_different_id_in_path_still_pairs() -> None:
    """Path with dynamic ID + same query → fuzzy path match keeps the pair."""
    base = [_rec("GET", "http://h/admin/api-keys/apk_A?fields=id,title")]
    target = [_rec("GET", "http://h/admin/api-keys/apk_B?fields=id,title")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1


def test_short_dynamic_value_in_query_still_pairs() -> None:
    """Short dynamic-like values (e.g. q=test-1a64e3) must still pair.

    Regression for the bug where a value-shape regex missed short
    prefix-style identifiers and split otherwise-identical URLs into two
    different APIs. Structural matching on query KEYS only — values get
    compared later as content, not as identity — fixes this.
    """
    base = [_rec("GET", "http://h/admin/api-keys?limit=20&offset=0&q=test-1a64e3&type=publishable&fields=id,title")]
    target = [_rec("GET", "http://h/admin/api-keys?limit=20&offset=0&q=test-726260&type=publishable&fields=id,title")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1


def test_dynamic_id_in_query_value_still_pairs() -> None:
    """Query strings whose only difference is a dynamic ID value must pair.

    Regression for publishable-api-keys-crud step 8, where each run created a
    different apk_id and the resulting `?publishable_key_id=apk_…` URLs
    were treated as separate APIs by exact-query matching.
    """
    base = [_rec("GET", "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJQZKQXYQ6VZZP0F8738Y8S")]
    target = [_rec("GET", "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJR6BPMZSWTBVA0VQT0VV25")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1


def test_extra_query_key_does_not_pair() -> None:
    """An additional query key changes the API identity, even with the same dynamic ID."""
    base = [_rec("GET", "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJQZKQXYQ6VZZP0F8738Y8S")]
    target = [_rec("GET", "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJR6BPMZSWTBVA0VQT0VV25&extra=foo")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert paired == []


def test_repeated_same_url_pairs_in_occurrence_order() -> None:
    """Same URL fired N times → pair by occurrence order (timestamps)."""
    base = [
        _rec("GET", "http://h/admin/x?a=1", status=200, timestamp="2026-05-14T00:00:01"),
        _rec("GET", "http://h/admin/x?a=1", status=304, timestamp="2026-05-14T00:00:02"),
        _rec("GET", "http://h/admin/x?a=1", status=200, timestamp="2026-05-14T00:00:03"),
    ]
    target = [
        _rec("GET", "http://h/admin/x?a=1", status=200, timestamp="2026-05-14T00:00:01"),
        _rec("GET", "http://h/admin/x?a=1", status=304, timestamp="2026-05-14T00:00:02"),
        _rec("GET", "http://h/admin/x?a=1", status=200, timestamp="2026-05-14T00:00:03"),
    ]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 3
    # First-with-first, etc.
    for p in paired:
        assert p.baseline["status_code"] == p.target["status_code"]
