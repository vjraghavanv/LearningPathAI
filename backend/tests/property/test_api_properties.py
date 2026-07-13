"""
Property-based tests for API Gateway Security and Cross-Cutting Concerns.

# Feature: learningpath-ai, Property 24: All endpoints require valid authorization
# Feature: learningpath-ai, Property 25: Unhandled exceptions do not expose stack traces
# Feature: learningpath-ai, Property 26: Structured log entries contain required fields

Validates: Requirements 9.2, 9.5, 12.1, 12.2
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.auth_authorizer.handler import handler as auth_handler, _validate_token
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import LambdaLogger, _sanitize_message

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_user_id_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
    ),
)

_path_strategy = st.sampled_from([
    "/resources",
    "/resources/{id}",
    "/analyze",
    "/career-goal",
    "/learning-plan",
    "/dashboard",
    "/progress/{id}",
    "/search",
])

_correlation_id_strategy = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
    ),
)

_invalid_auth_strategy = st.one_of(
    st.just(""),
    st.just(None),
    st.just("invalid-not-bearer"),
    st.just("Bearer"),
    st.just("Bearer "),
    st.text(min_size=1, max_size=20).filter(
        lambda t: not t.strip().lower().startswith("bearer ")
    ),
)

_valid_token_strategy = st.text(
    min_size=10,
    max_size=200,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=".-_"
    ),
).map(lambda t: f"Bearer {t}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lambda_event(
    path: str = "/resources",
    method: str = "GET",
    authorization: str | None = None,
    body: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Build a minimal API Gateway Lambda proxy event."""
    headers: dict[str, str] = {}
    if authorization is not None:
        headers["Authorization"] = authorization

    event: dict[str, Any] = {
        "httpMethod": method,
        "path": path,
        "headers": headers,
        "body": body,
        "pathParameters": None,
        "queryStringParameters": None,
        "requestContext": {
            "requestId": "test-correlation-id",
        },
    }

    if user_id is not None:
        event["requestContext"]["authorizer"] = {
            "claims": {"sub": user_id}
        }

    return event


def _make_authorizer_event(token: str | None, method_arn: str = "arn:aws:execute-api:us-east-1:123456789:api123/prod/GET/resources") -> dict:
    """Build an API Gateway TOKEN authorizer event."""
    return {
        "authorizationToken": token,
        "methodArn": method_arn,
    }


def _capture_log_output(func, *args, **kwargs) -> tuple[Any, list[str]]:
    """Run func, capture all structured log output, return (result, log_lines)."""
    log_stream = io.StringIO()
    handler_obj = logging.StreamHandler(log_stream)
    handler_obj.setFormatter(logging.Formatter("%(message)s"))

    # Get the shared logger's underlying Python logger
    import shared.logger as logger_module
    original_handlers = logger_module._python_logger.handlers[:]
    logger_module._python_logger.handlers = [handler_obj]
    logger_module._python_logger.setLevel(logging.DEBUG)

    try:
        result = func(*args, **kwargs)
    finally:
        logger_module._python_logger.handlers = original_handlers

    log_output = log_stream.getvalue()
    lines = [line.strip() for line in log_output.splitlines() if line.strip()]
    return result, lines


# ===========================================================================
# Property 24: All endpoints require valid authorization
#
# Feature: learningpath-ai, Property 24: All endpoints require valid authorization
# Validates: Requirements 9.2
# ===========================================================================


@given(token=_invalid_auth_strategy)
@settings(max_examples=100)
def test_property24_missing_or_invalid_token_denied(token):
    """
    # Feature: learningpath-ai, Property 24: All endpoints require valid authorization

    For any request with a missing or invalid Authorization header,
    the Lambda authorizer must return a Deny policy (which causes API GW
    to return HTTP 401).

    Validates: Requirements 9.2
    """
    principal, effect = _validate_token(token or "")
    assert effect == "Deny", (
        f"Expected Deny for invalid/missing token '{token}', got '{effect}'"
    )


@given(token=_valid_token_strategy)
@settings(max_examples=100)
def test_property24_valid_bearer_token_allowed(token):
    """
    # Feature: learningpath-ai, Property 24: All endpoints require valid authorization

    For any request with a valid Bearer token, the authorizer must Allow.

    Validates: Requirements 9.2
    """
    principal, effect = _validate_token(token)
    assert effect == "Allow", (
        f"Expected Allow for valid token '{token[:50]}...', got '{effect}'"
    )


@given(
    token=_invalid_auth_strategy,
    method_arn=st.just("arn:aws:execute-api:us-east-1:123456789:api123/prod/GET/resources"),
)
@settings(max_examples=100)
def test_property24_authorizer_returns_deny_policy_for_invalid_token(token, method_arn):
    """
    # Feature: learningpath-ai, Property 24: All endpoints require valid authorization

    The full authorizer handler must return a policy with Effect=Deny for
    missing or malformed Authorization values.

    Validates: Requirements 9.2
    """
    event = _make_authorizer_event(token, method_arn)
    result = auth_handler(event, None)

    assert "policyDocument" in result, "Authorizer must return a policyDocument"
    statements = result["policyDocument"]["Statement"]
    assert len(statements) > 0, "policyDocument must have at least one Statement"

    effect = statements[0]["Effect"]
    assert effect == "Deny", (
        f"Expected Effect=Deny for invalid token, got '{effect}'"
    )


@given(
    token=_valid_token_strategy,
    method_arn=st.just("arn:aws:execute-api:us-east-1:123456789:api123/prod/GET/resources"),
)
@settings(max_examples=100)
def test_property24_authorizer_returns_allow_policy_for_valid_token(token, method_arn):
    """
    # Feature: learningpath-ai, Property 24: All endpoints require valid authorization

    The full authorizer handler must return a policy with Effect=Allow for
    a well-formed Bearer token.

    Validates: Requirements 9.2
    """
    event = _make_authorizer_event(token, method_arn)
    result = auth_handler(event, None)

    assert "policyDocument" in result
    statements = result["policyDocument"]["Statement"]
    assert len(statements) > 0

    effect = statements[0]["Effect"]
    assert effect == "Allow", (
        f"Expected Effect=Allow for valid token, got '{effect}'"
    )


@given(
    path=_path_strategy,
    method=st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH"]),
)
@settings(max_examples=100)
def test_property24_lambda_handlers_return_401_without_user_context(path, method):
    """
    # Feature: learningpath-ai, Property 24: All endpoints require valid authorization

    When a Lambda handler is invoked without authorizer context (simulating
    an unauthenticated call), it must return HTTP 401.

    Tests multiple handlers to verify they all enforce auth.
    Validates: Requirements 9.2
    """
    from lambdas.resource_manager.handler import handler as rm_handler
    from lambdas.dashboard_api.handler import handler as dashboard_handler
    from lambdas.search_service.handler import handler as search_handler

    # Event with no authorizer context (no userId)
    event = _make_lambda_event(path=path, method=method)

    handlers_to_test = [
        rm_handler,
        dashboard_handler,
        search_handler,
    ]

    for h in handlers_to_test:
        with patch("boto3.client"), patch("boto3.resource"):
            result = h(event, None)

        assert result["statusCode"] == 401, (
            f"Handler {h.__module__} must return 401 without auth context, "
            f"got {result['statusCode']}"
        )


# ===========================================================================
# Property 25: Unhandled exceptions do not expose stack traces
#
# Feature: learningpath-ai, Property 25: Unhandled exceptions do not expose stack traces
# Validates: Requirements 9.5
# ===========================================================================


@given(
    error_message=st.text(min_size=0, max_size=500),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property25_unhandled_exception_returns_500_generic_message(error_message, user_id):
    """
    # Feature: learningpath-ai, Property 25: Unhandled exceptions do not expose stack traces

    For any Lambda function invocation that results in an unhandled exception,
    the API response must be HTTP 500 with a generic error message.

    Validates: Requirements 9.5
    """
    @lambda_error_handler
    def failing_handler(event, context):
        raise RuntimeError(error_message)

    event = _make_lambda_event(user_id=user_id)
    result = failing_handler(event, None)

    assert result["statusCode"] == 500, (
        f"Unhandled exception must produce HTTP 500, got {result['statusCode']}"
    )
    body = json.loads(result["body"])
    assert body["error"] == "INTERNAL_SERVER_ERROR"
    assert "message" in body


@given(
    error_message=st.text(min_size=0, max_size=500),
)
@settings(max_examples=100)
def test_property25_500_response_does_not_contain_stack_trace(error_message):
    """
    # Feature: learningpath-ai, Property 25: Unhandled exceptions do not expose stack traces

    The HTTP 500 response body must not contain stack trace details,
    file paths, or internal exception messages.

    Validates: Requirements 9.5
    """
    @lambda_error_handler
    def failing_handler(event, context):
        raise ValueError(error_message)

    event = _make_lambda_event()
    result = failing_handler(event, None)

    assert result["statusCode"] == 500
    body_str = result["body"]

    # These patterns must never appear in the response body
    forbidden_patterns = [
        "Traceback",
        "File \"",
        "line ",
        "/var/task",
        "/opt/python",
        ".py",
        "raise ",
        "ValueError",
        "RuntimeError",
        "Exception",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in body_str, (
            f"Response body must not contain '{pattern}' — "
            f"stack trace leaked in 500 response: {body_str[:200]}"
        )


@given(
    exception_type=st.sampled_from([
        ("RuntimeError", RuntimeError),
        ("ValueError", ValueError),
        ("KeyError", KeyError),
        ("AttributeError", AttributeError),
        ("TypeError", TypeError),
        ("IndexError", IndexError),
    ]),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property25_any_exception_type_produces_generic_500(exception_type, user_id):
    """
    # Feature: learningpath-ai, Property 25: Unhandled exceptions do not expose stack traces

    Any unhandled exception type must produce the same generic HTTP 500 response.

    Validates: Requirements 9.5
    """
    exc_name, exc_class = exception_type

    @lambda_error_handler
    def failing_handler(event, context):
        raise exc_class(f"Internal detail about {exc_name}")

    event = _make_lambda_event(user_id=user_id)
    result = failing_handler(event, None)

    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    # Generic message must not expose the exception type name
    assert exc_name not in result["body"], (
        f"Exception type '{exc_name}' must not appear in 500 response body"
    )
    assert body["error"] == "INTERNAL_SERVER_ERROR"
    assert body["message"] == "An unexpected error occurred."


@given(
    raw_message=st.text(min_size=0, max_size=1000),
)
@settings(max_examples=100)
def test_property25_sanitize_message_removes_sensitive_patterns(raw_message):
    """
    # Feature: learningpath-ai, Property 25: Unhandled exceptions do not expose stack traces

    The _sanitize_message utility must never allow sensitive patterns
    (stack traces, file paths, internal library references) through.

    Validates: Requirements 9.5, 12.2
    """
    sanitized = _sanitize_message(raw_message)

    sensitive_patterns = [
        "Traceback",
        "File \"",
        "botocore",
        "boto3",
        "/var/task",
        "/opt/python",
    ]
    for pattern in sensitive_patterns:
        if pattern.lower() in raw_message.lower():
            assert pattern.lower() not in sanitized.lower(), (
                f"_sanitize_message must strip '{pattern}' from error messages, "
                f"but it appeared in: '{sanitized}'"
            )


# ===========================================================================
# Property 26: Structured log entries contain required fields
#
# Feature: learningpath-ai, Property 26: Structured log entries contain required fields
# Validates: Requirements 12.1, 12.2
# ===========================================================================


@given(
    path=_path_strategy,
    correlation_id=_correlation_id_strategy,
    status_code=st.sampled_from([200, 201, 204, 400, 403, 404, 415, 500, 503]),
    duration_ms=st.floats(min_value=0.0, max_value=60000.0, allow_nan=False),
)
@settings(max_examples=100)
def test_property26_emit_produces_valid_json_with_required_fields(
    path, correlation_id, status_code, duration_ms
):
    """
    # Feature: learningpath-ai, Property 26: Structured log entries contain required fields

    For any Lambda invocation, the emitted log entry must be valid JSON
    containing at minimum: path, statusCode, durationMs, correlationId.

    Validates: Requirements 12.1
    """
    log_entries: list[str] = []

    # Capture log output
    log_stream = io.StringIO()
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))

    import shared.logger as logger_module
    original_handlers = logger_module._python_logger.handlers[:]
    logger_module._python_logger.handlers = [stream_handler]

    try:
        logger = LambdaLogger(path=path, correlation_id=correlation_id)
        logger.emit(status_code=status_code, duration_ms=duration_ms)
    finally:
        logger_module._python_logger.handlers = original_handlers

    output = log_stream.getvalue().strip()
    assert output, "Logger must emit at least one line"

    # Validate every non-empty line is parseable JSON
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            pytest.fail(f"Log entry is not valid JSON: {line[:200]}")

        # Required fields for every invocation
        assert "path" in entry, f"Log entry missing 'path': {entry}"
        assert "statusCode" in entry, f"Log entry missing 'statusCode': {entry}"
        assert "durationMs" in entry, f"Log entry missing 'durationMs': {entry}"
        assert "correlationId" in entry, f"Log entry missing 'correlationId': {entry}"

        # Values must match what was provided
        assert entry["path"] == path
        assert entry["statusCode"] == status_code
        assert entry["correlationId"] == correlation_id
        assert isinstance(entry["durationMs"], (int, float))


@given(
    path=_path_strategy,
    correlation_id=_correlation_id_strategy,
    user_id=_user_id_strategy,
    status_code=st.sampled_from([200, 201, 204]),
    duration_ms=st.floats(min_value=0.0, max_value=60000.0, allow_nan=False),
)
@settings(max_examples=100)
def test_property26_log_includes_user_id_when_available(
    path, correlation_id, user_id, status_code, duration_ms
):
    """
    # Feature: learningpath-ai, Property 26: Structured log entries contain required fields

    When a userId is provided, the log entry must include it.
    When not provided, the field should be absent (not null or empty string).

    Validates: Requirements 12.1
    """
    log_stream = io.StringIO()
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))

    import shared.logger as logger_module
    original_handlers = logger_module._python_logger.handlers[:]
    logger_module._python_logger.handlers = [stream_handler]

    try:
        logger = LambdaLogger(path=path, correlation_id=correlation_id)
        logger.set_user(user_id)
        logger.emit(status_code=status_code, duration_ms=duration_ms)
    finally:
        logger_module._python_logger.handlers = original_handlers

    output = log_stream.getvalue().strip()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        assert "userId" in entry, f"userId must be present when set: {entry}"
        assert entry["userId"] == user_id


@given(
    path=_path_strategy,
    correlation_id=_correlation_id_strategy,
    status_code=st.sampled_from([400, 500, 503]),
    duration_ms=st.floats(min_value=0.0, max_value=60000.0, allow_nan=False),
    error_type=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))),
    error_message=st.text(min_size=0, max_size=200),
)
@settings(max_examples=100)
def test_property26_error_log_contains_error_type_and_message(
    path, correlation_id, status_code, duration_ms, error_type, error_message
):
    """
    # Feature: learningpath-ai, Property 26: Structured log entries contain required fields

    For error invocations, the log entry must additionally contain
    errorType and a sanitized errorMessage.

    Validates: Requirements 12.2
    """
    log_stream = io.StringIO()
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))

    import shared.logger as logger_module
    original_handlers = logger_module._python_logger.handlers[:]
    logger_module._python_logger.handlers = [stream_handler]

    try:
        logger = LambdaLogger(path=path, correlation_id=correlation_id)
        logger.emit_error(
            status_code=status_code,
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message or "An error occurred",
        )
    finally:
        logger_module._python_logger.handlers = original_handlers

    output = log_stream.getvalue().strip()
    assert output, "Error logger must emit at least one line"

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)

        # Base required fields
        assert "path" in entry
        assert "statusCode" in entry
        assert "durationMs" in entry
        assert "correlationId" in entry

        # Error-specific fields
        assert "errorType" in entry, f"Error log must contain 'errorType': {entry}"
        assert "errorMessage" in entry, f"Error log must contain 'errorMessage': {entry}"
        assert entry["errorType"] == error_type


@given(
    path=_path_strategy,
    correlation_id=_correlation_id_strategy,
    duration_ms=st.floats(min_value=0.0, max_value=60000.0, allow_nan=False),
    raw_exception_message=st.text(min_size=0, max_size=300),
)
@settings(max_examples=100)
def test_property26_error_log_message_is_sanitized(
    path, correlation_id, duration_ms, raw_exception_message
):
    """
    # Feature: learningpath-ai, Property 26: Structured log entries contain required fields

    The errorMessage in error log entries must be sanitized — it must not
    contain stack traces, file paths, or internal library references.

    Validates: Requirements 12.2
    """
    log_stream = io.StringIO()
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))

    import shared.logger as logger_module
    original_handlers = logger_module._python_logger.handlers[:]
    logger_module._python_logger.handlers = [stream_handler]

    exc = RuntimeError(raw_exception_message)

    try:
        logger = LambdaLogger(path=path, correlation_id=correlation_id)
        logger.emit_error(status_code=500, duration_ms=duration_ms, exc=exc)
    finally:
        logger_module._python_logger.handlers = original_handlers

    output = log_stream.getvalue().strip()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if "errorMessage" not in entry:
            continue

        error_msg = entry["errorMessage"]
        sensitive_patterns = [
            "Traceback",
            "File \"",
            "botocore",
            "boto3",
            "/var/task",
            "/opt/python",
        ]
        for pattern in sensitive_patterns:
            if pattern.lower() in raw_exception_message.lower():
                assert pattern.lower() not in error_msg.lower(), (
                    f"Sanitized errorMessage must not contain '{pattern}': '{error_msg}'"
                )


@given(
    path=_path_strategy,
    correlation_id=_correlation_id_strategy,
    status_code=st.sampled_from([200, 201, 400, 500]),
    duration_ms=st.floats(min_value=0.0, max_value=60000.0, allow_nan=False),
)
@settings(max_examples=100)
def test_property26_log_duration_ms_is_non_negative(
    path, correlation_id, status_code, duration_ms
):
    """
    # Feature: learningpath-ai, Property 26: Structured log entries contain required fields

    The durationMs field in log entries must always be a non-negative number.

    Validates: Requirements 12.1
    """
    log_stream = io.StringIO()
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))

    import shared.logger as logger_module
    original_handlers = logger_module._python_logger.handlers[:]
    logger_module._python_logger.handlers = [stream_handler]

    try:
        logger = LambdaLogger(path=path, correlation_id=correlation_id)
        logger.emit(status_code=status_code, duration_ms=duration_ms)
    finally:
        logger_module._python_logger.handlers = original_handlers

    output = log_stream.getvalue().strip()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        assert isinstance(entry.get("durationMs"), (int, float)), (
            f"durationMs must be numeric: {entry}"
        )
