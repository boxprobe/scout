"""Tests for matcher/normalize.py — URL path normalization."""

from scout.matcher.normalize import extract_dynamic_pairs, normalize_query, normalize_url, paths_match


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


# -- normalize_query ----------------------------------------------------------


def test_normalize_query_empty() -> None:
    assert normalize_query("") == ""


def test_normalize_query_prefixed_id_masked() -> None:
    """Prefixed IDs (apk_..., region_..., etc.) → masked."""
    a = normalize_query("limit=10&offset=0&publishable_key_id=apk_01KRJQZKQXYQ6VZZP0F8738Y8S")
    b = normalize_query("limit=10&offset=0&publishable_key_id=apk_01KRJR6BPMZSWTBVA0VQT0VV25")
    assert a == b
    assert "publishable_key_id=*" in a


def test_normalize_query_non_dynamic_values_preserved() -> None:
    """Short integers and enums must survive normalization."""
    assert normalize_query("limit=10") == "limit=10"
    assert normalize_query("type=publishable") == "type=publishable"
    assert normalize_query("offset=0") == "offset=0"


def test_normalize_query_different_limit_not_same() -> None:
    """limit=10 and limit=20 are different APIs in a paginated list."""
    assert normalize_query("limit=10") != normalize_query("limit=20")


def test_normalize_query_extra_key_not_same() -> None:
    """Adding a new query key changes the API identity."""
    a = normalize_query("limit=10&offset=0&publishable_key_id=apk_ABCDEFGHIJ")
    b = normalize_query("limit=10&offset=0&publishable_key_id=apk_ABCDEFGHIJ&extra=foo")
    assert a != b


def test_normalize_query_uuid_masked() -> None:
    a = normalize_query("user=f47ac10b-58cc-4372-a567-0e02b2c3d479")
    b = normalize_query("user=12345678-90ab-4cde-9012-3456789abcde")
    assert a == b == "user=*"


def test_normalize_query_sorted_canonical() -> None:
    """Different key order normalizes to the same canonical string."""
    a = normalize_query("limit=10&offset=0")
    b = normalize_query("offset=0&limit=10")
    assert a == b


def test_normalize_query_long_digit_string_masked() -> None:
    """8+ digit numbers (timestamps, big ids) treated as dynamic."""
    a = normalize_query("created_at=1716800000")
    b = normalize_query("created_at=1716900000")
    assert a == b
