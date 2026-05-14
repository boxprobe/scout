"""Tests for matcher/normalize.py — URL path normalization."""

from scout.matcher.normalize import (
    extract_dynamic_pairs,
    extract_query_dynamic_pairs,
    normalize_url,
    paths_match,
    query_key_set,
)


def test_strip_query_params() -> None:
    """URL is reduced to method + path, query params stripped."""
    assert normalize_url("http://localhost:19000/admin/orders?limit=20&offset=0") == "/admin/orders"


def test_strip_scheme_and_host() -> None:
    assert normalize_url("https://api.example.com/v1/users") == "/v1/users"


def test_trailing_slash() -> None:
    assert normalize_url("http://localhost/admin/") == "/admin"


def test_paths_match_identical() -> None:
    """Identical paths match."""
    assert paths_match("/admin/orders", "/admin/orders") is True


def test_paths_match_different_id_segment() -> None:
    """Paths differing only in one segment (likely ID) match."""
    assert paths_match("/admin/orders/ord_ABC", "/admin/orders/ord_XYZ") is True


def test_paths_match_different_id_preserves_context() -> None:
    """Nested paths with ID segments match when structure is same."""
    assert paths_match(
        "/admin/orders/ord_ABC/items",
        "/admin/orders/ord_XYZ/items",
    ) is True


def test_paths_match_different_endpoints() -> None:
    """Structurally different paths do not match."""
    assert paths_match("/admin/orders", "/admin/users") is False


def test_paths_match_different_length() -> None:
    """Paths with different segment counts do not match."""
    assert paths_match("/admin/orders", "/admin/orders/123/items") is False


def test_paths_match_multiple_id_segments() -> None:
    """Multiple ID segments can differ."""
    assert paths_match(
        "/admin/orders/ord_A/items/item_1",
        "/admin/orders/ord_B/items/item_2",
    ) is True


def test_paths_match_all_segments_differ() -> None:
    """If ALL segments differ, paths don't match (not just IDs)."""
    assert paths_match("/foo/bar/baz", "/qux/quux/corge") is False


def test_extract_dynamic_pairs_single() -> None:
    """One diverging ID segment yields one pair."""
    pairs = extract_dynamic_pairs("/admin/orders/ord_ABC", "/admin/orders/ord_XYZ")
    assert pairs == [("ord_ABC", "ord_XYZ")]


def test_extract_dynamic_pairs_multiple() -> None:
    """Multiple diverging ID segments yield ordered pairs (path order preserved)."""
    pairs = extract_dynamic_pairs(
        "/admin/orders/ord_A/items/item_1",
        "/admin/orders/ord_B/items/item_2",
    )
    assert pairs == [("ord_A", "ord_B"), ("item_1", "item_2")]


def test_extract_dynamic_pairs_identical() -> None:
    """Identical paths have no diverging segments."""
    assert extract_dynamic_pairs("/admin/orders", "/admin/orders") == []


def test_extract_dynamic_pairs_length_mismatch() -> None:
    """Different segment counts → no pairs (not extractable)."""
    assert extract_dynamic_pairs("/admin/orders", "/admin/orders/ord_X") == []


def test_extract_dynamic_pairs_skips_literal_match() -> None:
    """Literal-matching segments don't produce pairs even when ID-shaped."""
    pairs = extract_dynamic_pairs(
        "/orgs/org_FIXED/projects/proj_A",
        "/orgs/org_FIXED/projects/proj_B",
    )
    assert pairs == [("proj_A", "proj_B")]


def test_extract_dynamic_pairs_pure_int() -> None:
    """Pure integer ID segments are extractable too."""
    assert extract_dynamic_pairs("/users/123", "/users/456") == [("123", "456")]


# -- query_key_set + extract_query_dynamic_pairs ------------------------------


def test_query_key_set_empty() -> None:
    assert query_key_set("") == ()


def test_query_key_set_sorted_canonical() -> None:
    """Same keys in different order produce the same set."""
    assert query_key_set("limit=10&offset=0") == query_key_set("offset=0&limit=10")


def test_query_key_set_values_irrelevant() -> None:
    """Whether values differ or look like IDs doesn't matter — only key names do.

    Two requests with the same key set are the same logical API; value
    differences are surfaced later by body comparison.
    """
    a = query_key_set("limit=10&offset=0&publishable_key_id=apk_01KRJQZKQXYQ6VZZP0F8738Y8S")
    b = query_key_set("limit=10&offset=0&publishable_key_id=apk_01KRJR6BPMZSWTBVA0VQT0VV25")
    assert a == b


def test_query_key_set_extra_key_differs() -> None:
    """Adding a query key is a real API identity change."""
    a = query_key_set("limit=10&offset=0&publishable_key_id=apk_AAA")
    b = query_key_set("limit=10&offset=0&publishable_key_id=apk_AAA&extra=foo")
    assert a != b


def test_query_key_set_short_value_still_grouped() -> None:
    """Short string values (e.g. q=test-1a64e3) get the same treatment as long IDs.

    Regression for the bug where a regex-based heuristic missed short
    prefix-style IDs and split otherwise-identical URLs into separate APIs.
    """
    a = query_key_set("limit=20&offset=0&q=test-1a64e3&type=publishable")
    b = query_key_set("limit=20&offset=0&q=test-726260&type=publishable")
    assert a == b


def test_extract_query_dynamic_pairs_value_diff() -> None:
    """For shared keys with differing values, return (value_a, value_b)."""
    pairs = extract_query_dynamic_pairs(
        "limit=10&q=test-1a64e3&type=publishable",
        "limit=10&q=test-726260&type=publishable",
    )
    assert pairs == [("test-1a64e3", "test-726260")]


def test_extract_query_dynamic_pairs_identical_no_pair() -> None:
    pairs = extract_query_dynamic_pairs("limit=10&offset=0", "limit=10&offset=0")
    assert pairs == []


def test_extract_query_dynamic_pairs_unmatched_keys_ignored() -> None:
    """Keys only present on one side are not extracted — alignment handles those."""
    pairs = extract_query_dynamic_pairs("limit=10&extra=foo", "limit=20")
    # limit differs (extracted); extra exists only on baseline (ignored here)
    assert pairs == [("10", "20")]


def test_extract_query_dynamic_pairs_multiple() -> None:
    pairs = extract_query_dynamic_pairs(
        "q=test-A&publishable_key_id=apk_AAA&fields=id",
        "q=test-B&publishable_key_id=apk_BBB&fields=id",
    )
    # Keys are processed in sorted order
    assert pairs == [("apk_AAA", "apk_BBB"), ("test-A", "test-B")]
