"""
Top-level Lambda error handler for LearningPath AI.

Provides:
  - api_response(status_code, body)  — builds a consistent API Gateway proxy response dict.
  - lambda_error_handler(handler)    — decorator that wraps a Lambda handler function,
                                       catches any unhandled exception, logs it at ERROR
                                       level, and returns HTTP 500 with a generic message.

Design rationale (Requirement 9.5, Property 25):
  When a Lambda function returns an unhandled exception, the API Gateway SHALL return
  HTTP 500 with a generic error message and SHALL NOT expose internal stack traces or
  system details to the caller.

Usage::

    from shared.error_handler import lambda_error_handler, api_response

    @lambda_error_handler
    def handler(event, context):
        # Any unhandled exception here is caught and returns HTTP 500.
        return api_response(200, {"message": "OK"})
"""

import functools
import json
import time
from typing import Any, Callable

from shared.logger import LambdaLogger, InvocationTimer, make_logger

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def api_response(status_code: int, body: Any) -> dict:
    """
    Build an API Gateway Lambda proxy integration response.

    Args:
        status_code: HTTP status code (e.g. 200, 400, 500).
        body:        Response body — will be JSON-serialised if not already a string.

    Returns:
        A dict with ``statusCode``, ``headers``, and ``body`` keys as required by
        the API Gateway Lambda proxy integration contract.
    """
    if not isinstance(body, str):
        body = json.dumps(body)

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": body,
    }


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def lambda_error_handler(handler: Callable) -> Callable:
    """
    Decorator that wraps a Lambda handler with a top-level exception catcher.

    Behaviour:
      - On success: passes the handler's return value through unchanged.
      - On any unhandled exception:
          1. Logs the error at ERROR level via the shared LambdaLogger using a
             sanitized message (no stack traces, file paths, or internal details).
          2. Returns an API Gateway proxy response with HTTP 500 and a generic
             ``{"error": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}``
             body.

    The decorator is transparent for the happy path — it does not modify the
    response when the wrapped handler succeeds.

    Example::

        @lambda_error_handler
        def handler(event, context):
            return api_response(200, {"data": "hello"})
    """

    @functools.wraps(handler)
    def wrapper(event: dict, context: Any) -> dict:
        timer = InvocationTimer()
        logger: LambdaLogger = make_logger(event, context)

        try:
            return handler(event, context)
        except Exception as exc:
            duration_ms = timer.elapsed_ms()
            logger.emit_error(
                status_code=500,
                duration_ms=duration_ms,
                exc=exc,
            )
            return api_response(
                500,
                {
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                },
            )

    return wrapper
