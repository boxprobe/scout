"""Tests for matcher/align.py — endpoint sequence alignment."""

from scout.matcher.align import align_records


def _rec(method: str, url: str, status: int = 200, timestamp: str = "") -> dict:
    """Minimal record dict for testing."""
    return {
        "method": method,
        "url": url,
        "status_code": status,
        "response_body": None,
        "timestamp": timestamp,
    }


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


def test_same_path_different_query_still_pairs_stage1_first() -> None:
    """Same path with reordered parallel queries: stage 1 pairs by query key set.

    Both sides fired the same two filter URLs in opposite arrival order;
    stage 1 of the two-stage alignment groups identical-query-shape records
    together regardless of position.
    """
    base = [
        _rec("GET", "http://h/admin/api-keys?q=&limit=3&fields=id"),
        _rec("GET", "http://h/admin/api-keys?limit=20&offset=0&type=publishable"),
    ]
    target = [
        _rec("GET", "http://h/admin/api-keys?limit=20&offset=0&type=publishable"),
        _rec("GET", "http://h/admin/api-keys?q=&limit=3&fields=id"),
    ]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 2
    for p in paired:
        # Stage-1 matches always have identical query strings on both sides
        assert p.baseline["url"] == p.target["url"]


def test_same_path_query_differs_still_pairs_stage2() -> None:
    """Different query strings on the same path still pair (stage 2).

    Path identity defines the endpoint. ``?fields=*address`` vs
    ``?fields=name,metadata,…`` is the SAME endpoint called with different
    field subsets — alignment must pair them so the diff report can show
    the query difference inline instead of inflating the endpoint-change
    count.
    """
    base = [_rec("GET", "http://h/admin/api-keys?q=&limit=3")]
    target = [_rec("GET", "http://h/admin/api-keys?limit=20&offset=0")]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1
    assert paired[0].baseline["url"] != paired[0].target["url"]


def test_two_stage_pairing_prefers_exact_query_match() -> None:
    """When some records share a query and some don't, stage 1 wins first.

    Regression for medusa stock-locations: each side fired the same
    ``?fields=*address`` short query plus a full ``?fields=…`` query
    whose item list differed. Stage 1 must pair the short queries to each
    other, leaving the fulls (different item lists) to pair via stage 2.
    """
    base = [
        _rec("GET", "http://h/admin/x?fields=name,a,b", timestamp="t1"),
        _rec("GET", "http://h/admin/x?fields=address", timestamp="t2"),
    ]
    target = [
        _rec("GET", "http://h/admin/x?fields=address", timestamp="t1"),
        _rec("GET", "http://h/admin/x?fields=name,a,b,c", timestamp="t2"),
    ]
    result = align_records(base, target)
    paired = [(p.baseline["url"], p.target["url"]) for p in result if p.baseline and p.target]
    assert len(paired) == 2
    # The short query pair survives intact
    assert ("http://h/admin/x?fields=address", "http://h/admin/x?fields=address") in paired
    # The other pair has differing queries (the +c item)
    assert ("http://h/admin/x?fields=name,a,b", "http://h/admin/x?fields=name,a,b,c") in paired


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
    base = [
        _rec(
            "GET",
            "http://h/admin/api-keys?limit=20&offset=0&q=test-1a64e3&type=publishable&fields=id,title",
        )
    ]
    target = [
        _rec(
            "GET",
            "http://h/admin/api-keys?limit=20&offset=0&q=test-726260&type=publishable&fields=id,title",
        )
    ]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1


def test_dynamic_id_in_query_value_still_pairs() -> None:
    """Query strings whose only difference is a dynamic ID value must pair.

    Regression for publishable-api-keys-crud step 8, where each run created a
    different apk_id and the resulting `?publishable_key_id=apk_…` URLs
    were treated as separate APIs by exact-query matching.
    """
    base = [
        _rec(
            "GET",
            "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJQZKQXYQ6VZZP0F8738Y8S",
        )
    ]
    target = [
        _rec(
            "GET",
            "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJR6BPMZSWTBVA0VQT0VV25",
        )
    ]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1


def test_extra_query_key_still_pairs_via_stage2() -> None:
    """Extra query key on target — same path → still pair, query diff surfaced later."""
    base = [
        _rec(
            "GET",
            "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJQZKQXYQ6VZZP0F8738Y8S",
        )
    ]
    target = [
        _rec(
            "GET",
            "http://h/admin/sales-channels?limit=10&offset=0&publishable_key_id=apk_01KRJR6BPMZSWTBVA0VQT0VV25&extra=foo",
        )
    ]
    result = align_records(base, target)
    paired = [p for p in result if p.baseline and p.target]
    assert len(paired) == 1


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
