"""
Unit tests for backend/shared/logger.py

Validates:
 - Requirement 12.1: structured JSON logs include userId, path, statusCode, durationMs, correlationId
 - Requirement 12.2: error logs include errorType and sanitized errorMessage
"""

import json
import logging
import sys
import os

import pytest

# Allow imports from backend/shared without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.logger import (
    LambdaLogger,
    InvocationTimer,
    _sanitize_message,
    make_logger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class CapturingHandler(logging.Handler):
    """Captures log records emitted to the shared._python_logger."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def last_json(self) -> dict:
        assert self.records, "No log records captured"
        return json.loads(self.records[-1].getMessage())


def make_capturing_logger() -> tuple[LambdaLogger, CapturingHandler]:
    """Return a LambdaLogger wired to a CapturingHandler for inspection."""
    import shared.logger as _mod

    handler = CapturingHandler()
    _mod._python_logger.addHandler(handler)
    logger = LambdaLogger(path="/test/path", correlation_id="corr-001")
    return logger, handler


def teardown_capturing(handler: CapturingHandler) -> None:
    import shared.logger as _mod
    _mod._python_logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# emit() — successful invocations
# ---------------------------------------------------------------------------

class TestEmitSuccess:
    def test_contains_path(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=200, duration_ms=50.0)
            assert handler.last_json()["path"] == "/test/path"
        finally:
            teardown_capturing(handler)

    def test_contains_status_code(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=201, duration_ms=10.0)
            assert handler.last_json()["statusCode"] == 201
        finally:
            teardown_capturing(handler)

    def test_contains_duration_ms(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=200, duration_ms=123.456)
            assert handler.last_json()["durationMs"] == pytest.approx(123.456, abs=0.001)
        finally:
            teardown_capturing(handler)

    def test_contains_correlation_id(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=200, duration_ms=5.0)
            assert handler.last_json()["correlationId"] == "corr-001"
        finally:
            teardown_capturing(handler)

    def test_contains_user_id_when_set(self):
        logger, handler = make_capturing_logger()
        try:
            logger.set_user("user-abc")
            logger.emit(status_code=200, duration_ms=5.0)
            assert handler.last_json()["userId"] == "user-abc"
        finally:
            teardown_capturing(handler)

    def test_no_user_id_when_not_set(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=200, duration_ms=5.0)
            assert "userId" not in handler.last_json()
        finally:
            teardown_capturing(handler)

    def test_log_level_is_info(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=200, duration_ms=5.0)
            assert handler.records[-1].levelno == logging.INFO
        finally:
            teardown_capturing(handler)

    def test_output_is_valid_json(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit(status_code=200, duration_ms=5.0)
            raw = handler.records[-1].getMessage()
            parsed = json.loads(raw)
            assert isinstance(parsed, dict)
        finally:
            teardown_capturing(handler)


# ---------------------------------------------------------------------------
# emit_error() — error invocations
# ---------------------------------------------------------------------------

class TestEmitError:
    def test_contains_all_base_fields(self):
        logger, handler = make_capturing_logger()
        try:
            logger.set_user("user-xyz")
            logger.emit_error(status_code=500, duration_ms=20.0, exc=ValueError("boom"))
            entry = handler.last_json()
            for field in ("path", "statusCode", "durationMs", "correlationId", "userId"):
                assert field in entry, f"Missing field: {field}"
        finally:
            teardown_capturing(handler)

    def test_contains_error_type_from_exception(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit_error(status_code=500, duration_ms=5.0, exc=KeyError("k"))
            assert handler.last_json()["errorType"] == "KeyError"
        finally:
            teardown_capturing(handler)

    def test_contains_error_message(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit_error(status_code=500, duration_ms=5.0, exc=RuntimeError("bad thing"))
            assert "errorMessage" in handler.last_json()
        finally:
            teardown_capturing(handler)

    def test_error_type_override(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit_error(status_code=500, duration_ms=5.0, error_type="CustomError")
            assert handler.last_json()["errorType"] == "CustomError"
        finally:
            teardown_capturing(handler)

    def test_error_message_override(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit_error(status_code=500, duration_ms=5.0, error_message="Something failed")
            assert handler.last_json()["errorMessage"] == "Something failed"
        finally:
            teardown_capturing(handler)

    def test_log_level_is_error(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit_error(status_code=500, duration_ms=5.0)
            assert handler.records[-1].levelno == logging.ERROR
        finally:
            teardown_capturing(handler)

    def test_no_stack_trace_in_error_message(self):
        try:
            raise ValueError("original error")
        except ValueError as e:
            logger, handler = make_capturing_logger()
            try:
                logger.emit_error(status_code=500, duration_ms=5.0, exc=e)
                entry = handler.last_json()
                assert "Traceback" not in entry["errorMessage"]
                assert "File \"" not in entry["errorMessage"]
            finally:
                teardown_capturing(handler)

    def test_no_exc_produces_generic_message(self):
        logger, handler = make_capturing_logger()
        try:
            logger.emit_error(status_code=500, duration_ms=5.0)
            entry = handler.last_json()
            assert entry["errorType"] == "UnknownError"
            assert entry["errorMessage"]
        finally:
            teardown_capturing(handler)


# ---------------------------------------------------------------------------
# _sanitize_message
# ---------------------------------------------------------------------------

class TestSanitizeMessage:
    def test_plain_message_unchanged(self):
        assert _sanitize_message("Resource not found") == "Resource not found"

    def test_traceback_keyword_scrubbed(self):
        result = _sanitize_message("Traceback (most recent call last):\n  File...")
        assert result == "An internal error occurred"

    def test_file_path_scrubbed(self):
        result = _sanitize_message('File "/var/task/handler.py", line 42')
        assert result == "An internal error occurred"

    def test_botocore_mention_scrubbed(self):
        result = _sanitize_message("botocore.exceptions.ClientError: error")
        assert result == "An internal error occurred"

    def test_long_message_truncated(self):
        long_msg = "x" * 600
        result = _sanitize_message(long_msg)
        assert len(result) <= 504  # 500 chars + ellipsis (…)
        assert result.endswith("…")

    def test_empty_message_returns_generic(self):
        assert _sanitize_message("") == "An internal error occurred"

    def test_multiline_keeps_first_line_only(self):
        result = _sanitize_message("First line\nSecond line with Traceback details")
        assert result == "First line"


# ---------------------------------------------------------------------------
# InvocationTimer
# ---------------------------------------------------------------------------

class TestInvocationTimer:
    def test_elapsed_ms_is_non_negative(self):
        timer = InvocationTimer()
        assert timer.elapsed_ms() >= 0

    def test_elapsed_ms_increases_over_time(self):
        import time
        timer = InvocationTimer()
        time.sleep(0.01)
        assert timer.elapsed_ms() >= 10.0


# ---------------------------------------------------------------------------
# make_logger factory
# ---------------------------------------------------------------------------

class TestMakeLogger:
    def _event(self, path="/resources", request_id="req-999"):
        return {
            "path": path,
            "requestContext": {"requestId": request_id},
        }

    def test_returns_lambda_logger_instance(self):
        logger = make_logger(self._event(), context=None)
        assert isinstance(logger, LambdaLogger)

    def test_extracts_path(self):
        logger, handler = make_capturing_logger()
        teardown_capturing(handler)  # we'll inspect via emit
        logger2 = make_logger(self._event(path="/career-goal"), context=None)
        import shared.logger as _mod
        h = CapturingHandler()
        _mod._python_logger.addHandler(h)
        try:
            logger2.emit(200, 5.0)
            assert h.last_json()["path"] == "/career-goal"
        finally:
            _mod._python_logger.removeHandler(h)

    def test_extracts_correlation_id(self):
        import shared.logger as _mod
        h = CapturingHandler()
        _mod._python_logger.addHandler(h)
        try:
            logger = make_logger(self._event(request_id="corr-xyz"), context=None)
            logger.emit(200, 5.0)
            assert h.last_json()["correlationId"] == "corr-xyz"
        finally:
            _mod._python_logger.removeHandler(h)

    def test_missing_path_falls_back_to_unknown(self):
        import shared.logger as _mod
        h = CapturingHandler()
        _mod._python_logger.addHandler(h)
        try:
            logger = make_logger({}, context=None)
            logger.emit(200, 5.0)
            assert h.last_json()["path"] == "unknown"
        finally:
            _mod._python_logger.removeHandler(h)

    def test_missing_request_id_falls_back_to_unknown(self):
        import shared.logger as _mod
        h = CapturingHandler()
        _mod._python_logger.addHandler(h)
        try:
            logger = make_logger({"path": "/x"}, context=None)
            logger.emit(200, 5.0)
            assert h.last_json()["correlationId"] == "unknown"
        finally:
            _mod._python_logger.removeHandler(h)

    def test_uses_raw_path_when_path_absent(self):
        import shared.logger as _mod
        h = CapturingHandler()
        _mod._python_logger.addHandler(h)
        try:
            event = {"rawPath": "/raw-resources", "requestContext": {"requestId": "r1"}}
            logger = make_logger(event, context=None)
            logger.emit(200, 5.0)
            assert h.last_json()["path"] == "/raw-resources"
        finally:
            _mod._python_logger.removeHandler(h)
