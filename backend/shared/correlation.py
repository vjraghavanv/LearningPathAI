"""
Correlation ID propagation utility for LearningPath AI Lambda functions.

Implements end-to-end request tracing by extracting the correlation ID
(API Gateway requestContext.requestId) from the Lambda event, storing it
in a per-invocation context variable (contextvars), and making it available
to any downstream call within the same invocation (Bedrock, DynamoDB, etc.).

Usage in a Lambda handler::

    from shared.correlation import (
        extract_correlation_id,
        set_correlation_id,
        get_correlation_id,
        correlation_context,
    )

    def handler(event, context):
        # Option A — explicit set/get
        correlation_id = extract_correlation_id(event)
        set_correlation_id(correlation_id)
        ...
        cid = get_correlation_id()   # available anywhere in the call stack

        # Option B — context manager (preferred)
        with correlation_context(event):
            ...
            cid = get_correlation_id()

    # Forwarding the ID to Bedrock via a custom trace header:
    headers = build_correlation_headers()
    # Pass these in boto3 client call configuration or as HTTP headers.

Requirement 12.5: Lambda functions SHALL propagate a correlation ID (generated
at the API Gateway layer) through all downstream calls to Amazon Bedrock and
DynamoDB to enable end-to-end request tracing.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Generator, Optional

# ---------------------------------------------------------------------------
# Module-level ContextVar — one per Lambda invocation (thread-safe by default,
# and also safe for async handlers because contextvars are copy-on-enter in
# async tasks and the same value propagates within the same synchronous call
# stack that sets it).
# ---------------------------------------------------------------------------

#: The active correlation ID for the current Lambda invocation.
#: Defaults to "unknown" when not explicitly set.
_correlation_id_var: ContextVar[str] = ContextVar(
    "_correlation_id_var", default="unknown"
)

# ---------------------------------------------------------------------------
# Extraction helper
# ---------------------------------------------------------------------------


def extract_correlation_id(event: dict[str, Any]) -> str:
    """
    Extract the correlation ID from an API Gateway Lambda proxy event.

    The correlation ID is sourced from the API Gateway-injected
    ``event["requestContext"]["requestId"]``.  When the field is absent
    (e.g., in locally-invoked or test events) ``"unknown"`` is returned so
    that downstream callers always receive a non-null string.

    Args:
        event: The raw Lambda event dict as received from API Gateway.

    Returns:
        The correlation ID string, or ``"unknown"`` if not present.
    """
    request_context: dict[str, Any] = event.get("requestContext") or {}
    return request_context.get("requestId") or "unknown"


# ---------------------------------------------------------------------------
# ContextVar accessors
# ---------------------------------------------------------------------------


def set_correlation_id(correlation_id: str) -> None:
    """
    Store *correlation_id* in the current invocation context.

    This sets the value for the entire synchronous call stack that follows
    within the same Lambda invocation.  The value is automatically isolated
    per-invocation because Lambda reuses the execution environment
    sequentially (not concurrently for the same instance).

    Args:
        correlation_id: The correlation ID to store.  Should be the value
                        returned by :func:`extract_correlation_id`.
    """
    _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """
    Retrieve the correlation ID set for the current invocation.

    Returns:
        The correlation ID string, or ``"unknown"`` if
        :func:`set_correlation_id` has not been called.
    """
    return _correlation_id_var.get()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@contextmanager
def correlation_context(
    event: dict[str, Any],
) -> Generator[str, None, None]:
    """
    Context manager that sets the correlation ID for the duration of a block.

    Extracts the correlation ID from *event*, stores it, yields the ID to
    the caller, and resets the context variable to its previous value when
    the block exits (even on exception).  This makes the utility safe to use
    in nested or test scenarios without state leaking between invocations.

    Args:
        event: The raw Lambda event dict as received from API Gateway.

    Yields:
        The correlation ID that was extracted and set.

    Example::

        with correlation_context(event) as cid:
            # cid == get_correlation_id() throughout this block
            invoke_bedrock(...)
            write_to_dynamodb(...)
    """
    token = None
    try:
        correlation_id = extract_correlation_id(event)
        token = _correlation_id_var.set(correlation_id)
        yield correlation_id
    finally:
        if token is not None:
            _correlation_id_var.reset(token)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def with_correlation_id(func: Callable) -> Callable:
    """
    Decorator that extracts and sets the correlation ID before calling *func*.

    The decorated function must accept ``event`` as its first positional
    argument (i.e. it follows the ``handler(event, context)`` Lambda
    signature).  The correlation ID is set from ``event`` before the body
    executes, and the context variable is reset to its previous value
    afterward.

    Example::

        @with_correlation_id
        def handler(event, context):
            cid = get_correlation_id()  # already populated
            ...

    Args:
        func: A callable whose first argument is a Lambda event dict.

    Returns:
        The wrapped callable with correlation ID injection.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # args[0] is the Lambda event dict
        event = args[0] if args else kwargs.get("event", {})
        correlation_id = extract_correlation_id(event)
        token = _correlation_id_var.set(correlation_id)
        try:
            return func(*args, **kwargs)
        finally:
            _correlation_id_var.reset(token)

    return wrapper


# ---------------------------------------------------------------------------
# Downstream forwarding helpers
# ---------------------------------------------------------------------------


def build_correlation_headers() -> dict[str, str]:
    """
    Build a dict of HTTP headers suitable for forwarding the correlation ID
    to downstream services.

    The header ``X-Correlation-ID`` is a widely-recognised convention for
    propagating trace context over HTTP.  When making boto3 Bedrock
    ``InvokeModel`` calls you can attach these headers via the
    ``customUserAgent`` or as part of the request metadata depending on the
    SDK version.

    Returns:
        A mapping containing ``{"X-Correlation-ID": "<current correlation id>"}``

    Example::

        headers = build_correlation_headers()
        # Merge into bedrock call kwargs, or log alongside downstream calls.
    """
    return {"X-Correlation-ID": get_correlation_id()}


def get_bedrock_client_config() -> dict[str, str]:
    """
    Return a dict of metadata to embed in Bedrock boto3 client invocations.

    Since the AWS SDK does not expose a first-class correlation header on
    ``InvokeModel``, this helper provides a consistent dictionary that Lambda
    handlers can log alongside every Bedrock call so the correlation ID appears
    in CloudWatch next to the Bedrock request.

    Returns:
        ``{"correlationId": "<current correlation id>"}``

    Example::

        meta = get_bedrock_client_config()
        logger.info(json.dumps({"action": "bedrock_invoke", **meta}))
        response = bedrock_client.invoke_model(...)
    """
    return {"correlationId": get_correlation_id()}
