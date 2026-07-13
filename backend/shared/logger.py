"""
Structured JSON logger utility for LearningPath AI Lambda functions.

Emits JSON log entries to CloudWatch with the following fields on every invocation:
  - userId       : authenticated user ID (if available)
  - path         : endpoint path
  - statusCode   : HTTP status code returned
  - durationMs   : execution duration in milliseconds
  - correlationId: request correlation ID propagated from API Gateway

For error invocations, additionally emits:
  - errorType    : exception class name
  - errorMessage : sanitized error message (no stack trace, file paths, or internal details)

Requirement 12.1, 12.2 — Lambda functions SHALL emit structured JSON logs to CloudWatch.
"""

import json
import logging
import time
from typing import Any, Optional

# Module-level Python logger — CloudWatch captures its output automatically
_python_logger = logging.getLogger(__name__)
_python_logger.setLevel(logging.INFO)

# Ensure a StreamHandler is present (Lambda adds one by default, but be explicit)
if not _python_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _python_logger.addHandler(_handler)


class LambdaLogger:
    """
    Structured JSON logger for a single Lambda invocation.

    Usage::

        logger = LambdaLogger(path="/resources", correlation_id="abc-123")
        logger.set_user("user-456")

        # At the end of the handler, after you know the status code:
        logger.emit(status_code=200, duration_ms=42.5)

        # On error:
        logger.emit_error(
            status_code=500,
            duration_ms=18.3,
            exc=some_exception,
        )
    """

    def __init__(self, path: str, correlation_id: str) -> None:
        self._path: str = path
        self._correlation_id: str = correlation_id
        self._user_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_user(self, user_id: Optional[str]) -> None:
        """Attach the authenticated userId so it appears in every log entry."""
        self._user_id = user_id

    def emit(self, status_code: int, duration_ms: float) -> None:
        """
        Emit a structured INFO-level log entry for a successful invocation.

        Args:
            status_code: HTTP status code returned to the caller.
            duration_ms: Total invocation duration in milliseconds.
        """
        entry = self._base_entry(status_code, duration_ms)
        _python_logger.info(json.dumps(entry))

    def emit_error(
        self,
        status_code: int,
        duration_ms: float,
        exc: Optional[BaseException] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Emit a structured ERROR-level log entry for a failed invocation.

        Sanitizes the error message to avoid leaking stack traces, file paths,
        or internal implementation details (Requirement 12.2).

        Args:
            status_code:   HTTP status code returned to the caller.
            duration_ms:   Total invocation duration in milliseconds.
            exc:           The caught exception (optional).
            error_type:    Override for the error type string (optional).
            error_message: Override for the sanitized error message (optional).
        """
        entry = self._base_entry(status_code, duration_ms)

        resolved_error_type = (
            error_type
            if error_type is not None
            else (type(exc).__name__ if exc is not None else "UnknownError")
        )
        resolved_error_message = (
            error_message
            if error_message is not None
            else _sanitize_message(str(exc) if exc is not None else "An internal error occurred")
        )

        entry["errorType"] = resolved_error_type
        entry["errorMessage"] = resolved_error_message

        _python_logger.error(json.dumps(entry))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_entry(self, status_code: int, duration_ms: float) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "path": self._path,
            "statusCode": status_code,
            "durationMs": round(duration_ms, 3),
            "correlationId": self._correlation_id,
        }
        # Include userId only when available (Requirement 12.1: "if available")
        if self._user_id is not None:
            entry["userId"] = self._user_id
        return entry


# ---------------------------------------------------------------------------
# Convenience: invocation timer
# ---------------------------------------------------------------------------

class InvocationTimer:
    """
    Simple wall-clock timer for measuring Lambda invocation duration.

    Usage::

        timer = InvocationTimer()
        # ... do work ...
        duration = timer.elapsed_ms()
    """

    def __init__(self) -> None:
        self._start: float = time.monotonic()

    def elapsed_ms(self) -> float:
        """Return the elapsed time in milliseconds since construction."""
        return (time.monotonic() - self._start) * 1000.0


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

# Patterns that should never appear in externally-visible error messages.
_SENSITIVE_PATTERNS: tuple[str, ...] = (
    "Traceback",
    "File \"",
    "line ",
    "  File ",
    "botocore",
    "boto3",
    "dynamo",
    "/var/task",
    "/opt/python",
)


def _sanitize_message(raw_message: str) -> str:
    """
    Strip potentially sensitive details from an error message.

    Removes stack-trace fragments, file paths, and internal library names so
    that the log entry is safe to store and query without risk of leaking
    internal implementation details (Requirement 12.2).

    A single-line summary is returned.  If the message contains a newline
    (typical of multi-line exception output) only the first non-empty line is
    kept.
    """
    first_line = raw_message.strip().splitlines()[0] if raw_message.strip() else ""

    for pattern in _SENSITIVE_PATTERNS:
        if pattern.lower() in first_line.lower():
            return "An internal error occurred"

    # Truncate overly-long messages to avoid log bloat
    max_length = 500
    if len(first_line) > max_length:
        first_line = first_line[:max_length] + "…"

    return first_line or "An internal error occurred"


# ---------------------------------------------------------------------------
# Factory helper — used by Lambda handlers
# ---------------------------------------------------------------------------

def make_logger(event: dict[str, Any], context: Any) -> "LambdaLogger":
    """
    Construct a LambdaLogger from a raw API Gateway Lambda proxy event.

    Extracts:
      - path           from event["path"] or event["rawPath"]
      - correlation_id from the API Gateway request context
                       (event["requestContext"]["requestId"])

    The caller is responsible for calling ``logger.set_user(user_id)`` once
    the authorizer context has been parsed (typically from
    ``event["requestContext"]["authorizer"]["claims"]["sub"]``).

    Args:
        event:   The Lambda event dict as received from API Gateway.
        context: The Lambda context object (currently unused, reserved for future use).

    Returns:
        A configured LambdaLogger instance ready to use.
    """
    path: str = (
        event.get("path")
        or event.get("rawPath")
        or event.get("resource")
        or "unknown"
    )

    # API Gateway injects a unique requestId into the requestContext
    request_context: dict[str, Any] = event.get("requestContext") or {}
    correlation_id: str = request_context.get("requestId") or "unknown"

    return LambdaLogger(path=path, correlation_id=correlation_id)
