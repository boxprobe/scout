"""Tests for matcher/noise.py — diff noise reduction."""

import pytest

from scout.matcher.noise import (
    DiffIgnoreConfig,
    IgnoreRule,
    detect_value_type,
    filter_body,
    load_diff_ignore,
    should_ignore_value_diff,
)
from scout.matcher.compare import compare_pair


# -- detect_value_type --

class TestDetectValueType:
    def test_uuid(self):
        assert detect_value_type("550e8400-e29b-41d4-a716-446655440000") == "uuid"

    def test_uuid_uppercase(self):
        assert detect_value_type("550E8400-E29B-41D4-A716-446655440000") == "uuid"

    def test_iso_timestamp(self):
        assert detect_value_type("2026-05-07T12:30:00.000Z") == "iso_timestamp"

    def test_iso_timestamp_space(self):
        assert detect_value_type("2026-05-07 12:30:00") == "iso_timestamp"

    def test_unix_timestamp_int(self):
        assert detect_value_type(1780000000) == "unix_timestamp"

    def test_mock_name(self):
        assert detect_value_type("test-a1b2c3d4") == "mock_name"

    def test_mock_name_concatenated(self):
        assert detect_value_type("test-2c4daatest-28861e") == "mock_name"

    def test_mock_name_triple(self):
        assert detect_value_type("test-abcdeftest-123456test-789abc") == "mock_name"

    def test_mock_email(self):
        assert detect_value_type("test-abcd1234@example.com") == "mock_email"

    def test_date(self):
        assert detect_value_type("2026-05-07") == "date"

    def test_plain_string(self):
        assert detect_value_type("hello world") is None

    def test_regular_number(self):
        assert detect_value_type(42) is None

    def test_none(self):
        assert detect_value_type(None) is None

    def test_bool(self):
        assert detect_value_type(True) is None

    def test_prefixed_id(self):
        assert detect_value_type("apk_01KR05N5DPBTFA6NZK75ZXXBG6") == "prefixed_id"

    def test_prefixed_id_order(self):
        assert detect_value_type("order_01KR05P3ABCDEF1234567890") == "prefixed_id"

    def test_hex_token(self):
        assert detect_value_type("pk_4150f59c68f49687ec9f1db222566dbc41cf4a89fda8c4c2850334b8a84fa565") == "hex_token"


# -- filter_body --

class TestFilterBody:
    def test_remove_simple_field(self):
        body = {"id": 1, "name": "Alice", "created_at": "2026-01-01"}
        rule = IgnoreRule(fields=("created_at",))
        result = filter_body(body, rule)
        assert result == {"id": 1, "name": "Alice"}

    def test_remove_multiple_fields(self):
        body = {"id": 1, "created_at": "x", "updated_at": "y", "name": "z"}
        rule = IgnoreRule(fields=("created_at", "updated_at"))
        result = filter_body(body, rule)
        assert result == {"id": 1, "name": "z"}

    def test_remove_nested_field(self):
        body = {"data": {"id": 1, "created_at": "x"}}
        rule = IgnoreRule(fields=("created_at",))
        result = filter_body(body, rule)
        assert result == {"data": {"id": 1}}

    def test_remove_in_array(self):
        body = {"items": [{"id": 1, "updated_at": "x"}, {"id": 2, "updated_at": "y"}]}
        rule = IgnoreRule(fields=("updated_at",))
        result = filter_body(body, rule)
        assert result == {"items": [{"id": 1}, {"id": 2}]}

    def test_glob_pattern(self):
        body = {"auth_token": "abc", "refresh_token": "def", "name": "z"}
        rule = IgnoreRule(fields=("*_token",))
        result = filter_body(body, rule)
        assert result == {"name": "z"}

    def test_no_fields_passthrough(self):
        body = {"id": 1}
        rule = IgnoreRule()
        assert filter_body(body, rule) == {"id": 1}

    def test_non_dict_passthrough(self):
        rule = IgnoreRule(fields=("x",))
        assert filter_body("hello", rule) == "hello"
        assert filter_body(42, rule) == 42

    def test_list_body(self):
        body = [{"id": 1, "ts": "x"}, {"id": 2, "ts": "y"}]
        rule = IgnoreRule(fields=("ts",))
        result = filter_body(body, rule)
        assert result == [{"id": 1}, {"id": 2}]


# -- should_ignore_value_diff --

class TestShouldIgnoreValueDiff:
    def test_both_uuid(self):
        a = "550e8400-e29b-41d4-a716-446655440000"
        b = "660f9500-f30c-52e5-b827-557766551111"
        assert should_ignore_value_diff(a, b, ("uuid",)) is True

    def test_both_mock_name(self):
        assert should_ignore_value_diff("test-abc123", "test-def456", ("mock_name",)) is True

    def test_both_iso_timestamp(self):
        a = "2026-05-06T10:00:00Z"
        b = "2026-05-07T12:30:00Z"
        assert should_ignore_value_diff(a, b, ("iso_timestamp",)) is True

    def test_type_not_in_list(self):
        a = "550e8400-e29b-41d4-a716-446655440000"
        b = "660f9500-f30c-52e5-b827-557766551111"
        assert should_ignore_value_diff(a, b, ("iso_timestamp",)) is False

    def test_mixed_types(self):
        assert should_ignore_value_diff("test-abc", "2026-01-01T00:00:00Z", ("mock_name", "iso_timestamp")) is False

    def test_one_not_detected(self):
        assert should_ignore_value_diff("test-abc123", "hello", ("mock_name",)) is False

    def test_empty_types(self):
        assert should_ignore_value_diff("test-abc", "test-def", ()) is False


# -- DiffIgnoreConfig --

class TestDiffIgnoreConfig:
    def test_global_rule(self):
        cfg = DiffIgnoreConfig(fields=("created_at",), value_types=("uuid",))
        rule = cfg.rule_for("GET", "/admin/products")
        assert "created_at" in rule.fields
        assert "uuid" in rule.value_types

    def test_override_adds(self):
        cfg = DiffIgnoreConfig(
            fields=("created_at",),
            value_types=("uuid",),
            overrides=(
                ("GET /admin/orders/*", IgnoreRule(fields=("metadata",), value_types=("date",))),
            ),
        )
        rule = cfg.rule_for("GET", "/admin/orders/123")
        assert "created_at" in rule.fields
        assert "metadata" in rule.fields
        assert "uuid" in rule.value_types
        assert "date" in rule.value_types

    def test_override_removes(self):
        cfg = DiffIgnoreConfig(
            fields=("id", "created_at"),
            overrides=(
                ("* /admin/orders/*", IgnoreRule(fields=("!id",))),
            ),
        )
        rule = cfg.rule_for("POST", "/admin/orders/new")
        assert "id" not in rule.fields
        assert "created_at" in rule.fields

    def test_no_match(self):
        cfg = DiffIgnoreConfig(
            fields=("created_at",),
            overrides=(
                ("GET /admin/orders/*", IgnoreRule(fields=("extra",))),
            ),
        )
        rule = cfg.rule_for("GET", "/admin/products/1")
        assert "extra" not in rule.fields

    def test_wildcard_method(self):
        cfg = DiffIgnoreConfig(
            overrides=(
                ("* /admin/*", IgnoreRule(fields=("metadata",))),
            ),
        )
        rule = cfg.rule_for("DELETE", "/admin/foo")
        assert "metadata" in rule.fields


# -- load_diff_ignore --

class TestLoadDiffIgnore:
    def test_none(self):
        cfg = load_diff_ignore(None)
        assert cfg.fields == ()
        assert cfg.value_types == ()

    def test_empty_dict(self):
        cfg = load_diff_ignore({})
        assert cfg.fields == ()

    def test_full(self):
        cfg = load_diff_ignore({
            "fields": ["created_at", "updated_at"],
            "value_types": ["uuid", "mock_name"],
            "overrides": [
                {
                    "pattern": "GET /admin/orders/*",
                    "fields": ["!id"],
                    "value_types": ["date"],
                }
            ],
        })
        assert cfg.fields == ("created_at", "updated_at")
        assert cfg.value_types == ("uuid", "mock_name")
        assert len(cfg.overrides) == 1
        assert cfg.overrides[0][0] == "GET /admin/orders/*"


# -- Integration: compare_pair with ignore --

class TestComparePairWithIgnore:
    def test_field_ignore_eliminates_diff(self):
        base = {"status_code": 200, "response_body": '{"id": 1, "created_at": "2026-01-01", "name": "x"}'}
        target = {"status_code": 200, "response_body": '{"id": 1, "created_at": "2026-02-01", "name": "x"}'}
        rule = IgnoreRule(fields=("created_at",))
        diff = compare_pair(base, target, ignore=rule)
        assert diff.value_match is True

    def test_value_type_ignore_eliminates_diff(self):
        base = {"status_code": 200, "response_body": '{"id": "550e8400-e29b-41d4-a716-446655440000", "name": "x"}'}
        target = {"status_code": 200, "response_body": '{"id": "660f9500-f30c-52e5-b827-557766551111", "name": "x"}'}
        rule = IgnoreRule(value_types=("uuid",))
        diff = compare_pair(base, target, ignore=rule)
        assert diff.value_match is True

    def test_mock_name_suppressed(self):
        base = {"status_code": 200, "response_body": '{"email": "test-abc12345@example.com", "role": "admin"}'}
        target = {"status_code": 200, "response_body": '{"email": "test-def67890@example.com", "role": "admin"}'}
        rule = IgnoreRule(value_types=("mock_email",))
        diff = compare_pair(base, target, ignore=rule)
        assert diff.value_match is True

    def test_real_diff_still_reported(self):
        base = {"status_code": 200, "response_body": '{"name": "Alice", "created_at": "2026-01-01"}'}
        target = {"status_code": 200, "response_body": '{"name": "Bob", "created_at": "2026-02-01"}'}
        rule = IgnoreRule(fields=("created_at",))
        diff = compare_pair(base, target, ignore=rule)
        assert diff.value_match is False
        assert "$.name" in diff.value_diff

    def test_no_ignore_unchanged_behavior(self):
        base = {"status_code": 200, "response_body": '{"a": 1}'}
        target = {"status_code": 200, "response_body": '{"a": 2}'}
        diff = compare_pair(base, target)
        assert diff.value_match is False

    def test_combined_field_and_value_type(self):
        base = {
            "status_code": 200,
            "response_body": '{"id": "550e8400-e29b-41d4-a716-446655440000", "ts": "2026-01-01T00:00:00Z", "count": 5}',
        }
        target = {
            "status_code": 200,
            "response_body": '{"id": "660f9500-f30c-52e5-b827-557766551111", "ts": "2026-02-02T12:00:00Z", "count": 5}',
        }
        rule = IgnoreRule(fields=("ts",), value_types=("uuid",))
        diff = compare_pair(base, target, ignore=rule)
        assert diff.value_match is True
