"""
DynamoDB client wrapper for LearningPath AI Lambda functions.

Provides a DynamoDBClient class that wraps boto3 DynamoDB operations with
automatic exponential backoff retry logic for throttling errors.

Retry behaviour:
  - Retries up to 3 times on ProvisionedThroughputExceededException or
    ThrottlingException (and its subclass RequestLimitExceeded).
  - Each retry waits 2^attempt * 100ms + a random jitter (0–100ms) to avoid
    thundering-herd effects.
  - After exhausting all retries, raises DynamoDBThrottlingError, which callers
    should surface as HTTP 503.

Design rationale (DynamoDB Transient Errors section):
  Lambda functions use exponential backoff with up to 3 retries for DynamoDB
  throttling errors before returning HTTP 503.

Usage::

    from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError

    db = DynamoDBClient(table_name="LearningPathAI")

    # get a single item
    item = db.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

    # put an item
    db.put_item(Item={"userId": "u1", "resourceId": "RESOURCE#abc", "title": "Intro"})

    # query by partition key
    import boto3.dynamodb.conditions as cond
    items = db.query(
        KeyConditionExpression=cond.Key("userId").eq("u1")
    )
"""

import random
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class DynamoDBThrottlingError(Exception):
    """
    Raised when a DynamoDB operation fails due to throttling after exhausting
    all retries (up to MAX_RETRIES attempts with exponential backoff).

    Callers should map this exception to an HTTP 503 response.
    """


# ---------------------------------------------------------------------------
# Retry configuration constants
# ---------------------------------------------------------------------------

#: Maximum number of retry attempts after the initial call fails.
MAX_RETRIES: int = 3

#: Base delay in milliseconds for the exponential backoff formula:
#:   delay = 2^attempt * BASE_DELAY_MS + jitter (0..JITTER_MS)
BASE_DELAY_MS: int = 100

#: Maximum random jitter added to each delay (milliseconds).
JITTER_MS: int = 100

#: DynamoDB error codes that should trigger a retry.
_THROTTLING_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ProvisionedThroughputExceededException",
        "ThrottlingException",
        "RequestLimitExceeded",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_throttling_error(exc: ClientError) -> bool:
    """Return True if the ClientError represents a DynamoDB throttling condition."""
    code = exc.response.get("Error", {}).get("Code", "")
    return code in _THROTTLING_ERROR_CODES


def _backoff_delay_seconds(attempt: int) -> float:
    """
    Compute the sleep duration for a given retry attempt (0-indexed).

    Formula: (2^attempt * BASE_DELAY_MS + random jitter) / 1000
    e.g. attempt 0 → ~100–200ms, attempt 1 → ~200–300ms, attempt 2 → ~400–500ms.
    """
    jitter = random.randint(0, JITTER_MS)
    delay_ms = (2 ** attempt) * BASE_DELAY_MS + jitter
    return delay_ms / 1000.0


# ---------------------------------------------------------------------------
# DynamoDBClient
# ---------------------------------------------------------------------------

class DynamoDBClient:
    """
    Thin wrapper around a boto3 DynamoDB Table resource with automatic
    exponential backoff retry for throttling errors.

    Args:
        table_name: The DynamoDB table name (defaults to ``LearningPathAI``).
        region_name: AWS region (optional; boto3 falls back to env/config).
        dynamodb_resource: Pre-built boto3 DynamoDB resource (optional;
                           useful for testing/mocking).
    """

    def __init__(
        self,
        table_name: str = "LearningPathAI",
        region_name: str | None = None,
        dynamodb_resource: Any | None = None,
    ) -> None:
        if dynamodb_resource is not None:
            self._resource = dynamodb_resource
        else:
            kwargs: dict[str, Any] = {"service_name": "dynamodb"}
            if region_name:
                kwargs["region_name"] = region_name
            self._resource = boto3.resource(**kwargs)

        self._table = self._resource.Table(table_name)

    # ------------------------------------------------------------------
    # Private retry executor
    # ------------------------------------------------------------------

    def _execute_with_retry(self, operation_name: str, fn, *args, **kwargs) -> Any:
        """
        Execute ``fn(*args, **kwargs)`` and retry up to MAX_RETRIES times on
        throttling errors with exponential backoff + jitter.

        Args:
            operation_name: Human-readable name used in the raised exception.
            fn: Callable that performs a single DynamoDB table operation.
            *args / **kwargs: Forwarded to ``fn``.

        Returns:
            The return value of ``fn``.

        Raises:
            DynamoDBThrottlingError: After MAX_RETRIES unsuccessful attempts.
            ClientError: Any non-throttling ClientError is re-raised immediately.
        """
        last_exc: ClientError | None = None

        for attempt in range(MAX_RETRIES + 1):  # attempt 0 is the initial call
            try:
                return fn(*args, **kwargs)
            except ClientError as exc:
                if _is_throttling_error(exc):
                    last_exc = exc
                    if attempt < MAX_RETRIES:
                        time.sleep(_backoff_delay_seconds(attempt))
                        continue  # retry
                    # Exhausted retries — fall through to raise below
                else:
                    raise  # Not a throttling error; propagate immediately

        raise DynamoDBThrottlingError(
            f"DynamoDB {operation_name} failed after {MAX_RETRIES} retries "
            f"due to throttling: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Public table operations
    # ------------------------------------------------------------------

    def get_item(self, **kwargs) -> dict[str, Any]:
        """
        Retrieve a single item by primary key.

        Args:
            **kwargs: Forwarded directly to ``Table.get_item()``.
                      Required: ``Key`` dict with ``userId`` and ``resourceId``.

        Returns:
            The full response dict from boto3 (contains ``Item`` key when found).

        Raises:
            DynamoDBThrottlingError: After MAX_RETRIES throttling failures.
            ClientError: For any other DynamoDB error.
        """
        return self._execute_with_retry(
            "get_item", self._table.get_item, **kwargs
        )

    def put_item(self, **kwargs) -> dict[str, Any]:
        """
        Create or fully overwrite an item.

        Args:
            **kwargs: Forwarded directly to ``Table.put_item()``.
                      Required: ``Item`` dict with ``userId`` and ``resourceId``.

        Returns:
            The boto3 response dict.

        Raises:
            DynamoDBThrottlingError: After MAX_RETRIES throttling failures.
            ClientError: For any other DynamoDB error.
        """
        return self._execute_with_retry(
            "put_item", self._table.put_item, **kwargs
        )

    def update_item(self, **kwargs) -> dict[str, Any]:
        """
        Update specific attributes of an existing item.

        Args:
            **kwargs: Forwarded directly to ``Table.update_item()``.
                      Required: ``Key`` dict and an update expression.

        Returns:
            The boto3 response dict.

        Raises:
            DynamoDBThrottlingError: After MAX_RETRIES throttling failures.
            ClientError: For any other DynamoDB error.
        """
        return self._execute_with_retry(
            "update_item", self._table.update_item, **kwargs
        )

    def delete_item(self, **kwargs) -> dict[str, Any]:
        """
        Delete an item by primary key.

        Args:
            **kwargs: Forwarded directly to ``Table.delete_item()``.
                      Required: ``Key`` dict with ``userId`` and ``resourceId``.

        Returns:
            The boto3 response dict.

        Raises:
            DynamoDBThrottlingError: After MAX_RETRIES throttling failures.
            ClientError: For any other DynamoDB error.
        """
        return self._execute_with_retry(
            "delete_item", self._table.delete_item, **kwargs
        )

    def query(self, **kwargs) -> dict[str, Any]:
        """
        Query items using a key condition expression.

        Args:
            **kwargs: Forwarded directly to ``Table.query()``.
                      Required: ``KeyConditionExpression``.

        Returns:
            The boto3 response dict (contains ``Items`` list).

        Raises:
            DynamoDBThrottlingError: After MAX_RETRIES throttling failures.
            ClientError: For any other DynamoDB error.
        """
        return self._execute_with_retry(
            "query", self._table.query, **kwargs
        )
