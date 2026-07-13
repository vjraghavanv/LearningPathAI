"""
Unit tests for backend/shared/error_handler.py

Validates:
  - Requirement 9.5: Unhandled Lambda exceptions return HTTP 500 with a generic message
                     and do NOT expose stack traces or system details.
  - api_response helper: consistent API Gateway proxy response structure.
  - lambda_error_handler decorator: transparent pass-through on success,
                                    safe HTTP 500 on unhandled exception.
"""

import json
import logging
import os
import sys

import pytest

# Allow imports from backend/shared without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.error_handler import api_response, lambda_error_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class CapturingHandler(logging.Handler):
    """Captures log records emitted to shared._python_logger."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def last_json(self) -> dict:
        assert self.records, "No log records captured"
        return json.loads(self.records[-1].getMessage())


def _attach_capture() -> CapturingHandler:
    import shared.logger as _mod
    handler = CapturingHandler()
    _mod._python_logger.addHandler(handler)
    return handler


def _detach_capture(handler: CapturingHandler) -> None:
    import shared.logger as _mod
    _mod._python_logger.removeHandler(handler)


def _make_event(path: str = "/test", request_id: str = "req-test-001") -> dict:
    return {
        "path": path,
        "requestContext": {"requestId": request_id},
    }


# ---------------------------------------------------------------------------
# api_response helper
# ---------------------------------------------------------------------------

class TestApiResponse:
    def test_status_code_set_correctly(self):
        response = api_response(200, {"ok": True})
        assert response["statusCode"] == 200

    def test_body_serialised_to_json_string(self):
        response = api_response(200, {"key": "value"})
        assert isinstance(response["body"], str)
        parsed = json.loads(response["body"])
        assert parsed == {"key": "value"}

    def test_string_body_passed_through_unchanged(self):
        raw = '{"already": "serialised"}'
        response = api_response(200, raw)
        assert response["body"] == raw

    def test_content_type_header_present(self):
        response = api_response(200, {})
        assert response["headers"]["Content-Type"] == "application/json"

    def test_returns_dict_with_required_keys(self):
        response = api_response(404, {"error": "Not found"})
        assert "statusCode" in response
        assert "headers" in response
        assert "body" in response

    def test_error_status_codes_supported(self):
        for status in (400, 401, 403, 404, 415, 429, 500, 503):
            response = api_response(status, {})
            assert response["statusCode"] == status

    def test_empty_dict_body(self):
        response = api_response(200, {})
        assert json.loads(response["body"]) == {}

    def test_list_body_serialised(self):
        response = api_response(200, [1, 2, 3])
        assert json.loads(response["body"]) == [1, 2, 3]


# ---------------------------------------------------------------------------
# lambda_error_handler — success path (transparent pass-through)
# ---------------------------------------------------------------------------

class TestLambdaErrorHandlerSuccess:
    def test_return_value_passed_through(self):
        expected = api_response(200, {"message": "OK"})

        @lambda_error_handler
        def handler(event, context):
            return expected

        result = handler(_make_event(), None)
        assert result == expected

    def test_does_not_swallow_non_exception_return(self):
        @lambda_error_handler
        def handler(event, context):
            return api_response(201, {"created": True})

        result = handler(_make_event(), None)
        assert result["statusCode"] == 201

    def test_decorated_function_name_preserved(self):
        @lambda_error_handler
        def my_lambda_handler(event, context):
            return api_response(200, {})

        assert my_lambda_handler.__name__ == "my_lambda_handler"

    def test_no_error_log_emitted_on_success(self):
        cap = _attach_capture()
        try:
            @lambda_error_handler
            def handler(event, context):
                return api_response(200, {})

            handler(_make_event(), None)
            error_records = [r for r in cap.records if r.levelno == logging.ERROR]
            assert len(error_records) == 0
        finally:
            _detach_capture(cap)


# ---------------------------------------------------------------------------
# lambda_error_handler — unhandled exception path
# ---------------------------------------------------------------------------

class TestLambdaErrorHandlerException:
    def test_returns_http_500_on_exception(self):
        @lambda_error_handler
        def handler(event, context):
            raise RuntimeError("something broke")

        result = handler(_make_event(), None)
        assert result["statusCode"] == 500

    def test_body_is_valid_json(self):
        @lambda_error_handler
        def handler(event, context):
            raise ValueError("bad input")

        result = handler(_make_event(), None)
        parsed = json.loads(result["body"])
        assert isinstance(parsed, dict)

    def test_body_contains_generic_message(self):
        @lambda_error_handler
        def handler(event, context):
            raise RuntimeError("internal detail that must not leak")

        result = handler(_make_event(), None)
        body = json.loads(result["body"])
        assert "message" in body
        assert body["message"] == "An unexpected error occurred."

    def test_body_contains_error_key(self):
        @lambda_error_handler
        def handler(event, context):
            raise KeyError("secret_key")

        result = handler(_make_event(), None)
        body = json.loads(result["body"])
        assert body["error"] == "INTERNAL_SERVER_ERROR"

    def test_no_stack_trace_in_response_body(self):
        @lambda_error_handler
        def handler(event, context):
            raise RuntimeError("boom")

        result = handler(_make_event(), None)
        body_str = result["body"]
        assert "Traceback" not in body_str
        assert "File \"" not in body_str
        assert "/var/task" not in body_str

    def test_no_internal_exception_message_in_response_body(self):
        secret_message = "super_secret_db_password_in_error"

        @lambda_error_handler
        def handler(event, context):
            raise RuntimeError(secret_message)

        result = handler(_make_event(), None)
        body_str = result["body"]
        # The raw exception message must not appear in the API response
        assert secret_message not in body_str

    def test_content_type_header_present_on_error(self):
        @lambda_error_handler
        def handler(event, context):
            raise Exception("oops")

        result = handler(_make_event(), None)
        assert result["headers"]["Content-Type"] == "application/json"

    def test_error_logged_at_error_level(self):
        cap = _attach_capture()
        try:
            @lambda_error_handler
            def handler(event, context):
                raise TypeError("type mismatch")

            handler(_make_event(), None)
            error_records = [r for r in cap.records if r.levelno == logging.ERROR]
            assert len(error_records) == 1
        finally:
            _detach_capture(cap)

    def test_logged_error_contains_error_type(self):
        cap = _attach_capture()
        try:
            @lambda_error_handler
            def handler(event, context):
                raise IndexError("out of bounds")

            handler(_make_event(), None)
            error_records = [r for r in cap.records if r.levelno == logging.ERROR]
            assert len(error_records) == 1
            log_entry = json.loads(error_records[0].getMessage())
            assert log_entry["errorType"] == "IndexError"
        finally:
            _detach_capture(cap)

    def test_logged_error_contains_sanitized_error_message(self):
        cap = _attach_capture()
        try:
            @lambda_error_handler
            def handler(event, context):
                raise RuntimeError("some user-visible message")

            handler(_make_event(), None)
            error_records = [r for r in cap.records if r.levelno == logging.ERROR]
            log_entry = json.loads(error_records[0].getMessage())
            assert "errorMessage" in log_entry
            # Must not contain stack trace keywords
            assert "Traceback" not in log_entry["errorMessage"]
        finally:
            _detach_capture(cap)

    def test_exception_subclasses_caught(self):
        """Verify that subclasses of Exception (not just base Exception) are caught."""

        class CustomAppError(ValueError):
            pass

        @lambda_error_handler
        def handler(event, context):
            raise CustomAppError("custom error")

        result = handler(_make_event(), None)
        assert result["statusCode"] == 500

    def test_different_exception_types_all_return_500(self):
        exception_types = [
            RuntimeError("runtime"),
            ValueError("value"),
            KeyError("key"),
            TypeError("type"),
            AttributeError("attr"),
            ZeroDivisionError("div zero"),
        ]

        for exc in exception_types:
            @lambda_error_handler
            def handler(event, context, _exc=exc):
                raise _exc

            result = handler(_make_event(), None)
            assert result["statusCode"] == 500, f"Expected 500 for {type(exc).__name__}"
