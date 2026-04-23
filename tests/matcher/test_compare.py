"""Tests for matcher/compare.py — API record comparison."""

from scout.matcher.compare import compare_pair, EndpointDiff


def test_identical_responses() -> None:
    """Same status + same structure but different values."""
    base = {"status_code": 200, "response_body": '{"users": [{"id": 1, "name": "Alice"}]}'}
    target = {"status_code": 200, "response_body": '{"users": [{"id": 2, "name": "Bob"}]}'}
    diff = compare_pair(base, target)
    assert diff.status_match is True
    assert diff.structure_match is True
    assert diff.value_match is False
    assert "$.users[0].id" in diff.value_diff
    assert "$.users[0].name" in diff.value_diff


def test_status_code_change() -> None:
    base = {"status_code": 200, "response_body": '{"ok": true}'}
    target = {"status_code": 500, "response_body": '{"error": "internal"}'}
    diff = compare_pair(base, target)
    assert diff.status_match is False
    assert diff.baseline_status == 200
    assert diff.target_status == 500


def test_structure_key_added() -> None:
    """Target has an extra key → structure mismatch."""
    base = {"status_code": 200, "response_body": '{"a": 1}'}
    target = {"status_code": 200, "response_body": '{"a": 1, "b": 2}'}
    diff = compare_pair(base, target)
    assert diff.structure_match is False
    assert "added" in diff.diff_summary.lower() or "b" in diff.diff_summary


def test_structure_key_removed() -> None:
    """Target missing a key → structure mismatch."""
    base = {"status_code": 200, "response_body": '{"a": 1, "b": 2}'}
    target = {"status_code": 200, "response_body": '{"a": 1}'}
    diff = compare_pair(base, target)
    assert diff.structure_match is False


def test_structure_type_change() -> None:
    """Same key but different type → structure mismatch."""
    base = {"status_code": 200, "response_body": '{"count": 5}'}
    target = {"status_code": 200, "response_body": '{"count": "five"}'}
    diff = compare_pair(base, target)
    assert diff.structure_match is False


def test_nested_structure_match() -> None:
    """Deeply nested identical structures match, values differ."""
    base = {"status_code": 200, "response_body": '{"data": {"items": [{"id": 1}]}}'}
    target = {"status_code": 200, "response_body": '{"data": {"items": [{"id": 99}]}}'}
    diff = compare_pair(base, target)
    assert diff.structure_match is True
    assert diff.value_match is False
    assert "$.data.items[0].id" in diff.value_diff


def test_value_match_identical() -> None:
    """Identical values → value_match True."""
    base = {"status_code": 200, "response_body": '{"count": 5, "ok": true}'}
    target = {"status_code": 200, "response_body": '{"count": 5, "ok": true}'}
    diff = compare_pair(base, target)
    assert diff.structure_match is True
    assert diff.value_match is True
    assert diff.value_diff == ""


def test_null_response_bodies() -> None:
    """Both null → match."""
    base = {"status_code": 204, "response_body": None}
    target = {"status_code": 204, "response_body": None}
    diff = compare_pair(base, target)
    assert diff.status_match is True
    assert diff.structure_match is True


def test_one_null_body() -> None:
    """One null, one not → structure mismatch."""
    base = {"status_code": 200, "response_body": '{"a": 1}'}
    target = {"status_code": 200, "response_body": None}
    diff = compare_pair(base, target)
    assert diff.structure_match is False


def test_non_json_body() -> None:
    """Non-JSON body treated as opaque — structure match if both non-JSON."""
    base = {"status_code": 200, "response_body": "OK"}
    target = {"status_code": 200, "response_body": "OK"}
    diff = compare_pair(base, target)
    assert diff.structure_match is True
