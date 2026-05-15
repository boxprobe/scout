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


# -- status_only schema: endpoint form (preferred) + legacy path fallback --

class TestStatusOnlySchema:
    def test_endpoint_form_method_match(self) -> None:
        """endpoint='GET /admin/orders' matches GET but not POST."""
        cfg = load_diff_ignore({
            "status_only": [
                {"endpoint": "GET /admin/orders", "scenario": "*", "step_seq": "*"},
            ]
        })
        assert cfg.is_status_only("any/scenario", "GET", "/admin/orders", 1) is True
        assert cfg.is_status_only("any/scenario", "POST", "/admin/orders", 1) is False

    def test_endpoint_form_wildcard_method(self) -> None:
        """endpoint='* /admin/orders' matches any method."""
        cfg = load_diff_ignore({
            "status_only": [
                {"endpoint": "* /admin/orders", "scenario": "*", "step_seq": "*"},
            ]
        })
        assert cfg.is_status_only("s", "GET", "/admin/orders", 1) is True
        assert cfg.is_status_only("s", "POST", "/admin/orders", 1) is True
        assert cfg.is_status_only("s", "DELETE", "/admin/orders", 1) is True

    def test_legacy_path_form(self) -> None:
        """Legacy entries with `path` (no `endpoint`) match any method."""
        cfg = load_diff_ignore({
            "status_only": [
                {"path": "/admin/orders", "scenario": "*", "step_seq": "*"},
            ]
        })
        assert cfg.is_status_only("s", "GET", "/admin/orders", 1) is True
        assert cfg.is_status_only("s", "POST", "/admin/orders", 1) is True

    def test_endpoint_form_with_path_glob(self) -> None:
        """endpoint='POST /admin/orders/*' matches POST + ID path."""
        cfg = load_diff_ignore({
            "status_only": [
                {"endpoint": "POST /admin/orders/*", "scenario": "*", "step_seq": "*"},
            ]
        })
        assert cfg.is_status_only("s", "POST", "/admin/orders/order_01HA", 1) is True
        assert cfg.is_status_only("s", "POST", "/admin/orders", 1) is False
        assert cfg.is_status_only("s", "GET",  "/admin/orders/order_01HA", 1) is False

    def test_endpoint_id_segments_auto_templatized(self) -> None:
        """Concrete IDs in endpoint path get auto-replaced with '*' on load,
        matching the same behavior as the legacy `path` form."""
        cfg = load_diff_ignore({
            "status_only": [
                {"endpoint": "DELETE /admin/api-keys/apk_01ABC", "scenario": "*", "step_seq": "*"},
            ]
        })
        # The concrete apk_01ABC should match any apk_* via templatization
        assert cfg.is_status_only("s", "DELETE", "/admin/api-keys/apk_99XYZ", 1) is True
        assert cfg.is_status_only("s", "DELETE", "/admin/api-keys", 1) is False

    def test_mixed_legacy_and_new_form(self) -> None:
        """Both forms can coexist in the same config."""
        cfg = load_diff_ignore({
            "status_only": [
                {"endpoint": "GET /admin/orders", "scenario": "*", "step_seq": "*"},
                {"path": "/admin/api-keys", "scenario": "*", "step_seq": "*"},
            ]
        })
        assert cfg.is_status_only("s", "GET", "/admin/orders", 1) is True
        assert cfg.is_status_only("s", "POST", "/admin/orders", 1) is False  # method-locked
        assert cfg.is_status_only("s", "POST", "/admin/api-keys", 1) is True  # legacy = any method

    def test_method_case_insensitive(self) -> None:
        """Method matching is case-insensitive."""
        cfg = load_diff_ignore({
            "status_only": [{"endpoint": "get /admin/orders", "scenario": "*", "step_seq": "*"}]
        })
        assert cfg.is_status_only("s", "GET", "/admin/orders", 1) is True
        assert cfg.is_status_only("s", "get", "/admin/orders", 1) is True

    def test_step_seq_still_filters(self) -> None:
        """step_seq narrowing still works alongside method filtering."""
        cfg = load_diff_ignore({
            "status_only": [
                {"endpoint": "GET /admin/orders", "scenario": "*", "step_seq": "3"},
            ]
        })
        assert cfg.is_status_only("s", "GET", "/admin/orders", 3) is True
        assert cfg.is_status_only("s", "GET", "/admin/orders", 4) is False


# -- header_ignore: extending the built-in DEFAULT_HEADER_IGNORE --

class TestHeaderIgnoreSchema:
    def test_loads_header_ignore_array(self) -> None:
        cfg = load_diff_ignore({
            "header_ignore": ["Access-Control-Allow-Origin", "X-Custom-Trace"],
        })
        # Lowercased on load for case-insensitive comparison
        assert "access-control-allow-origin" in cfg.header_ignore
        assert "x-custom-trace" in cfg.header_ignore

    def test_empty_when_field_absent(self) -> None:
        assert load_diff_ignore({}).header_ignore == ()

    def test_extra_ignore_suppresses_matching_header_in_diff(self) -> None:
        """compare_pair with header_ignore=('access-control-allow-origin',)
        should not produce a header_diff for that header even when it differs."""
        import json as _json
        baseline = {
            "status_code": 200,
            "response_body": '{}',
            "response_headers": _json.dumps({
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "http://localhost:19000",
            }),
        }
        target = {
            "status_code": 200,
            "response_body": '{}',
            "response_headers": _json.dumps({
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "http://localhost:29000",
            }),
        }
        # Without ignore: header_diff surfaces the change
        d1 = compare_pair(baseline, target)
        assert d1.header_match is False
        assert "access-control-allow-origin" in d1.header_diff
        # With ignore: silenced
        d2 = compare_pair(baseline, target, header_ignore=("access-control-allow-origin",))
        assert d2.header_match is True
        assert d2.header_diff == ""

    def test_default_ignores_still_apply(self) -> None:
        """Built-in DEFAULT_HEADER_IGNORE (Date, ETag, X-Request-ID, etc.) keeps
        working when extra_ignore is empty."""
        import json as _json
        baseline = {
            "status_code": 200,
            "response_body": '{}',
            "response_headers": _json.dumps({
                "Date": "Mon, 11 May 2026 00:00:00 GMT",
                "X-Request-ID": "abc123",
            }),
        }
        target = {
            "status_code": 200,
            "response_body": '{}',
            "response_headers": _json.dumps({
                "Date": "Mon, 11 May 2026 00:00:01 GMT",
                "X-Request-ID": "xyz999",
            }),
        }
        d = compare_pair(baseline, target)
        assert d.header_match is True
        assert d.header_diff == ""


# -- known_changes path syntax: [*] xpath-style AND [] jsonpath-style both valid --

class TestKnownChangeArrayWildcard:
    def test_xpath_star_wildcard_matches_concrete_index(self) -> None:
        """[*] wildcard already worked — keep regression coverage."""
        from scout.matcher.noise import filter_known_changes, KnownChange
        kc = (KnownChange(
            endpoint="GET /admin/collections",
            path="$.collections[*].external_id",
            change="added", since="2.14.0",
        ),)
        diff = "+ $.collections[0].external_id: null"
        result = filter_known_changes(diff, kc, "2.14.0", method="GET", api_path="/admin/collections")
        assert result == ""

    def test_rule_with_star_matches_diff_with_empty_brackets(self) -> None:
        """Rule path ``[*]`` must match the ``[]`` form that _json_schema emits.

        Regression: scout's structure differ emits ``$.collections[].field``
        for array fields, but users (and the popup's known-change buttons)
        write rules with ``[*]``. They denote the same thing — any element
        of the array — and the filter must accept both bracket forms.
        """
        from scout.matcher.noise import filter_known_changes, KnownChange
        kc = (KnownChange(
            endpoint="GET /admin/collections",
            path="$.collections[*].external_id",
            change="added", since="2.14.0",
        ),)
        diff = "+ $.collections[].external_id: null"
        result = filter_known_changes(diff, kc, "2.14.0", method="GET", api_path="/admin/collections")
        assert result == ""

    def test_jsonpath_empty_brackets_also_match(self) -> None:
        """[] (jsonpath shorthand for any index) should be equivalent to [*]."""
        from scout.matcher.noise import filter_known_changes, KnownChange
        kc = (KnownChange(
            endpoint="GET /admin/collections",
            path="$.collections[].external_id",
            change="added", since="2.14.0",
        ),)
        diff = "+ $.collections[0].external_id: null"
        result = filter_known_changes(diff, kc, "2.14.0", method="GET", api_path="/admin/collections")
        assert result == ""

    def test_mixed_wildcards_both_match(self) -> None:
        """Path with both [*] and [] should normalize uniformly."""
        from scout.matcher.noise import filter_known_changes, KnownChange
        kc = (KnownChange(
            endpoint="GET /admin/orders",
            path="$.orders[].items[*].sku",
            change="added", since="2.14.0",
        ),)
        diff = "+ $.orders[2].items[5].sku: string"
        result = filter_known_changes(diff, kc, "2.14.0", method="GET", api_path="/admin/orders")
        assert result == ""

    def test_concrete_index_doesnt_match_other_indices(self) -> None:
        """A rule with a literal [0] should NOT silence [1]. Wildcards are explicit."""
        from scout.matcher.noise import filter_known_changes, KnownChange
        kc = (KnownChange(
            endpoint="GET /admin/collections",
            path="$.collections[0].external_id",
            change="added", since="2.14.0",
        ),)
        diff = "+ $.collections[1].external_id: null"
        result = filter_known_changes(diff, kc, "2.14.0", method="GET", api_path="/admin/collections")
        assert result == diff  # not silenced
