"""
Unit tests for backend/shared/correlation.py

Validates:
 - Requirement 12.5: correlation ID is extracted from API Gateway event and
   propagated through all downstream calls via a context variable.
 - Correct extraction from requestContext.requestId
 - Fallback to "unknown" when fields are absent
 - set/get round-trip via ContextVar
 - Context manager isolates and resets state on exit (including exceptions)
 - Decorator correctly injects correlation ID from the Lambda event argument
 - Downstream forwarding helpers return the correct headers/config
"""

import os
import sys
from contextvars import copy_context
from typing import Any

import pytest

# Allow imports from backend/shared without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.correlation import (
    _correlation_id_var,
    build_correlation_headers,
    correlation_context,
    extract_correlation_id,
    get_bedrock_client_config,
    get_correlation_id,
    set_correlation_id,
    with_correlation_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api_gw_event(request_id: str = "req-abc123") -> dict[str, Any]:
    """Build a minimal API Gateway proxy event with a given requestId."""
    return {
        "path": "/resources",
        "requestContext": {"requestId": request_id},
    }


def _reset_correlation_id() -> None:
    """
    Reset the module-level ContextVar to its default ("unknown").

    Done by setting to the default so tests don't bleed into each other.
    """
    _correlation_id_var.set("unknown")


# ---------------------------------------------------------------------------
# extract_correlation_id
# ---------------------------------------------------------------------------


class TestExtractCorrelationId:
    def test_extracts_request_id_from_event(self):
        event = _api_gw_event("corr-001")
        assert extract_correlation_id(event) == "corr-001"

    def test_returns_unknown_when_request_context_missing(self):
        assert extract_correlation_id({}) == "unknown"

    def test_returns_unknown_when_request_id_key_absent(self):
        event = {"requestContext": {}}
        assert extract_correlation_id(event) == "unknown"

    def test_returns_unknown_when_request_id_is_none(self):
        event = {"requestContext": {"requestId": None}}
        assert extract_correlation_id(event) == "unknown"

    def test_returns_unknown_when_request_id_is_empty_string(self):
        event = {"requestContext": {"requestId": ""}}
        assert extract_correlation_id(event) == "unknown"

    def test_returns_actual_id_when_present(self):
        event = {"requestContext": {"requestId": "abc-xyz-789"}}
        assert extract_correlation_id(event) == "abc-xyz-789"

    def test_ignores_unrelated_event_fields(self):
        event = {
            "body": "{}",
            "headers": {"Authorization": "Bearer token"},
            "requestContext": {"requestId": "my-corr-id"},
        }
        assert extract_correlation_id(event) == "my-corr-id"


# ---------------------------------------------------------------------------
# set_correlation_id / get_correlation_id
# ---------------------------------------------------------------------------


class TestSetGetCorrelationId:
    def setup_method(self):
        _reset_correlation_id()

    def test_default_is_unknown(self):
        assert get_correlation_id() == "unknown"

    def test_set_and_get_round_trip(self):
        set_correlation_id("test-corr-id")
        assert get_correlation_id() == "test-corr-id"

    def test_set_overwrites_previous_value(self):
        set_correlation_id("first-id")
        set_correlation_id("second-id")
        assert get_correlation_id() == "second-id"

    def test_set_with_empty_string(self):
        set_correlation_id("")
        assert get_correlation_id() == ""

    def test_set_with_uuid_style_id(self):
        uuid_id = "550e8400-e29b-41d4-a716-446655440000"
        set_correlation_id(uuid_id)
        assert get_correlation_id() == uuid_id

    def test_context_isolation_between_copy_context_calls(self):
        """Values set in one copy_context do not affect the parent context."""
        set_correlation_id("parent-id")

        results = {}

        def child_task():
            set_correlation_id("child-id")
            results["child"] = get_correlation_id()

        ctx = copy_context()
        ctx.run(child_task)

        # Parent context should still hold "parent-id"
        assert get_correlation_id() == "parent-id"
        assert results["child"] == "child-id"


# ---------------------------------------------------------------------------
# correlation_context (context manager)
# ---------------------------------------------------------------------------


class TestCorrelationContext:
    def setup_method(self):
        _reset_correlation_id()

    def test_sets_correlation_id_within_block(self):
        event = _api_gw_event("ctx-001")
        with correlation_context(event) as cid:
            assert cid == "ctx-001"
            assert get_correlation_id() == "ctx-001"

    def test_yields_extracted_correlation_id(self):
        event = _api_gw_event("yielded-id")
        with correlation_context(event) as cid:
            assert cid == "yielded-id"

    def test_resets_to_previous_value_after_exit(self):
        set_correlation_id("before")
        event = _api_gw_event("during")
        with correlation_context(event):
            assert get_correlation_id() == "during"
        assert get_correlation_id() == "before"

    def test_resets_to_unknown_when_no_prior_value(self):
        event = _api_gw_event("temp-id")
        with correlation_context(event):
            pass
        assert get_correlation_id() == "unknown"

    def test_resets_on_exception(self):
        set_correlation_id("outer")
        event = _api_gw_event("inner")
        with pytest.raises(RuntimeError):
            with correlation_context(event):
                assert get_correlation_id() == "inner"
                raise RuntimeError("simulated error")
        # Context must be restored even after exception
        assert get_correlation_id() == "outer"

    def test_nested_context_managers(self):
        event_outer = _api_gw_event("outer-id")
        event_inner = _api_gw_event("inner-id")
        with correlation_context(event_outer) as outer_cid:
            assert outer_cid == "outer-id"
            with correlation_context(event_inner) as inner_cid:
                assert inner_cid == "inner-id"
                assert get_correlation_id() == "inner-id"
            # After inner exits, outer value should be restored
            assert get_correlation_id() == "outer-id"

    def test_fallback_to_unknown_in_context_for_missing_event(self):
        with correlation_context({}) as cid:
            assert cid == "unknown"
            assert get_correlation_id() == "unknown"

    def test_context_manager_can_be_used_multiple_times(self):
        event_a = _api_gw_event("req-A")
        event_b = _api_gw_event("req-B")
        with correlation_context(event_a):
            assert get_correlation_id() == "req-A"
        with correlation_context(event_b):
            assert get_correlation_id() == "req-B"
        assert get_correlation_id() == "unknown"


# ---------------------------------------------------------------------------
# with_correlation_id decorator
# ---------------------------------------------------------------------------


class TestWithCorrelationIdDecorator:
    def setup_method(self):
        _reset_correlation_id()

    def test_sets_correlation_id_inside_decorated_function(self):
        captured: list[str] = []

        @with_correlation_id
        def handler(event, context):
            captured.append(get_correlation_id())

        handler(_api_gw_event("dec-001"), None)
        assert captured == ["dec-001"]

    def test_resets_correlation_id_after_decorated_function_returns(self):
        set_correlation_id("before-dec")

        @with_correlation_id
        def handler(event, context):
            pass

        handler(_api_gw_event("dec-temp"), None)
        assert get_correlation_id() == "before-dec"

    def test_resets_correlation_id_after_decorated_function_raises(self):
        set_correlation_id("before-dec")

        @with_correlation_id
        def handler(event, context):
            raise ValueError("oops")

        with pytest.raises(ValueError):
            handler(_api_gw_event("dec-temp"), None)

        assert get_correlation_id() == "before-dec"

    def test_preserves_function_return_value(self):
        @with_correlation_id
        def handler(event, context):
            return {"statusCode": 200}

        result = handler(_api_gw_event("req-ret"), None)
        assert result == {"statusCode": 200}

    def test_preserves_function_name_via_functools_wraps(self):
        @with_correlation_id
        def my_handler(event, context):
            pass

        assert my_handler.__name__ == "my_handler"

    def test_fallback_when_event_has_no_request_context(self):
        captured: list[str] = []

        @with_correlation_id
        def handler(event, context):
            captured.append(get_correlation_id())

        handler({}, None)
        assert captured == ["unknown"]


# ---------------------------------------------------------------------------
# build_correlation_headers
# ---------------------------------------------------------------------------


class TestBuildCorrelationHeaders:
    def setup_method(self):
        _reset_correlation_id()

    def test_returns_dict_with_x_correlation_id_header(self):
        set_correlation_id("hdr-001")
        headers = build_correlation_headers()
        assert "X-Correlation-ID" in headers
        assert headers["X-Correlation-ID"] == "hdr-001"

    def test_reflects_current_correlation_id(self):
        set_correlation_id("first-id")
        assert build_correlation_headers()["X-Correlation-ID"] == "first-id"
        set_correlation_id("second-id")
        assert build_correlation_headers()["X-Correlation-ID"] == "second-id"

    def test_returns_unknown_when_not_set(self):
        headers = build_correlation_headers()
        assert headers["X-Correlation-ID"] == "unknown"

    def test_returns_dict(self):
        headers = build_correlation_headers()
        assert isinstance(headers, dict)


# ---------------------------------------------------------------------------
# get_bedrock_client_config
# ---------------------------------------------------------------------------


class TestGetBedrockClientConfig:
    def setup_method(self):
        _reset_correlation_id()

    def test_returns_dict_with_correlation_id_key(self):
        set_correlation_id("bedrock-001")
        config = get_bedrock_client_config()
        assert "correlationId" in config
        assert config["correlationId"] == "bedrock-001"

    def test_reflects_current_correlation_id(self):
        set_correlation_id("bedrock-A")
        assert get_bedrock_client_config()["correlationId"] == "bedrock-A"
        set_correlation_id("bedrock-B")
        assert get_bedrock_client_config()["correlationId"] == "bedrock-B"

    def test_returns_unknown_when_not_set(self):
        config = get_bedrock_client_config()
        assert config["correlationId"] == "unknown"

    def test_returns_dict(self):
        config = get_bedrock_client_config()
        assert isinstance(config, dict)


# ---------------------------------------------------------------------------
# Integration: full Lambda-like invocation flow
# ---------------------------------------------------------------------------


class TestCorrelationIntegration:
    def setup_method(self):
        _reset_correlation_id()

    def test_full_handler_flow_with_context_manager(self):
        """
        Simulate a Lambda handler that uses correlation_context and checks
        that downstream helpers return the correct ID throughout the call.
        """
        event = _api_gw_event("integration-001")

        with correlation_context(event) as cid:
            assert cid == "integration-001"
            headers = build_correlation_headers()
            bedrock_cfg = get_bedrock_client_config()

        assert headers["X-Correlation-ID"] == "integration-001"
        assert bedrock_cfg["correlationId"] == "integration-001"
        # After context exit, should reset to unknown
        assert get_correlation_id() == "unknown"

    def test_full_handler_flow_with_decorator(self):
        """Simulate a Lambda handler decorated with @with_correlation_id."""
        results: dict[str, Any] = {}

        @with_correlation_id
        def handler(event, context):
            results["cid"] = get_correlation_id()
            results["headers"] = build_correlation_headers()
            results["bedrock"] = get_bedrock_client_config()
            return {"statusCode": 200}

        response = handler(_api_gw_event("dec-integration"), None)

        assert response == {"statusCode": 200}
        assert results["cid"] == "dec-integration"
        assert results["headers"]["X-Correlation-ID"] == "dec-integration"
        assert results["bedrock"]["correlationId"] == "dec-integration"
        # Decorator should have reset the state
        assert get_correlation_id() == "unknown"

    def test_sequential_invocations_do_not_bleed(self):
        """Simulates two back-to-back Lambda invocations in the same process."""
        event1 = _api_gw_event("req-first")
        event2 = _api_gw_event("req-second")

        with correlation_context(event1):
            assert get_correlation_id() == "req-first"

        # Between invocations: should reset
        assert get_correlation_id() == "unknown"

        with correlation_context(event2):
            assert get_correlation_id() == "req-second"

        assert get_correlation_id() == "unknown"
