"""Tests for matcher/normalize.py — URL path normalization."""

from scout.matcher.normalize import extract_dynamic_pairs, normalize_url, paths_match


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
