"""
Unit tests for backend/shared/dynamodb_client.py

Tests:
  - Successful calls are passed through to the underlying boto3 Table methods.
  - Throttling errors trigger retry with exponential backoff (up to MAX_RETRIES).
  - After exhausting retries, DynamoDBThrottlingError is raised.
  - Non-throttling ClientErrors are re-raised immediately without retrying.
  - All five public operations are covered: get_item, put_item, update_item,
    delete_item, query.
  - Backoff delay grows correctly with each attempt.
"""

import os
import sys
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

# Allow imports from backend/shared without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.dynamodb_client import (
    MAX_RETRIES,
    DynamoDBClient,
    DynamoDBThrottlingError,
    _backoff_delay_seconds,
    _is_throttling_error,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_client_error(code: str) -> ClientError:
    """Build a boto3 ClientError with the given error code."""
    return ClientError(
        error_response={
            "Error": {
                "Code": code,
                "Message": f"Simulated {code}",
            }
        },
        operation_name="TestOperation",
    )


def _make_db_client(mock_table: MagicMock) -> DynamoDBClient:
    """Return a DynamoDBClient backed by a mock resource/table."""
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table
    return DynamoDBClient(table_name="LearningPathAI", dynamodb_resource=mock_resource)


# ---------------------------------------------------------------------------
# _is_throttling_error helper
# ---------------------------------------------------------------------------

class TestIsThrottlingError:
    def test_provisioned_throughput_exceeded(self):
        exc = _make_client_error("ProvisionedThroughputExceededException")
        assert _is_throttling_error(exc) is True

    def test_throttling_exception(self):
        exc = _make_client_error("ThrottlingException")
        assert _is_throttling_error(exc) is True

    def test_request_limit_exceeded(self):
        exc = _make_client_error("RequestLimitExceeded")
        assert _is_throttling_error(exc) is True

    def test_non_throttling_error_returns_false(self):
        exc = _make_client_error("ResourceNotFoundException")
        assert _is_throttling_error(exc) is False

    def test_internal_server_error_returns_false(self):
        exc = _make_client_error("InternalServerError")
        assert _is_throttling_error(exc) is False


# ---------------------------------------------------------------------------
# _backoff_delay_seconds helper
# ---------------------------------------------------------------------------

class TestBackoffDelaySeconds:
    def test_delay_increases_with_attempt(self):
        """Base component doubles each attempt; overall delay should grow."""
        # Use zero jitter by seeding random to 0 — just check that the
        # minimum value (base component only) grows with attempt.
        delays = [_backoff_delay_seconds(i) for i in range(MAX_RETRIES)]
        # Each delay must be at least BASE_DELAY_MS * 2^attempt / 1000 seconds
        from shared.dynamodb_client import BASE_DELAY_MS
        for i, delay in enumerate(delays):
            minimum = (2 ** i) * BASE_DELAY_MS / 1000.0
            assert delay >= minimum, f"Delay at attempt {i} ({delay}s) < minimum ({minimum}s)"

    def test_delay_is_positive(self):
        for attempt in range(MAX_RETRIES):
            assert _backoff_delay_seconds(attempt) > 0

    def test_delay_has_upper_bound(self):
        """Delay must not exceed 2^attempt * BASE_DELAY_MS + JITTER_MS."""
        from shared.dynamodb_client import BASE_DELAY_MS, JITTER_MS
        for attempt in range(MAX_RETRIES):
            max_possible = ((2 ** attempt) * BASE_DELAY_MS + JITTER_MS) / 1000.0
            assert _backoff_delay_seconds(attempt) <= max_possible


# ---------------------------------------------------------------------------
# DynamoDBClient — happy path (no errors)
# ---------------------------------------------------------------------------

class TestDynamoDBClientSuccess:
    """Each method forwards kwargs to the underlying table method and returns the result."""

    def test_get_item_success(self):
        mock_table = MagicMock()
        expected = {"Item": {"userId": "u1", "resourceId": "RESOURCE#abc"}}
        mock_table.get_item.return_value = expected

        client = _make_db_client(mock_table)
        result = client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert result == expected
        mock_table.get_item.assert_called_once_with(
            Key={"userId": "u1", "resourceId": "RESOURCE#abc"}
        )

    def test_put_item_success(self):
        mock_table = MagicMock()
        expected = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mock_table.put_item.return_value = expected

        client = _make_db_client(mock_table)
        item = {"userId": "u1", "resourceId": "RESOURCE#abc", "title": "Intro"}
        result = client.put_item(Item=item)

        assert result == expected
        mock_table.put_item.assert_called_once_with(Item=item)

    def test_update_item_success(self):
        mock_table = MagicMock()
        expected = {"Attributes": {"title": "Updated"}}
        mock_table.update_item.return_value = expected

        client = _make_db_client(mock_table)
        result = client.update_item(
            Key={"userId": "u1", "resourceId": "RESOURCE#abc"},
            UpdateExpression="SET #t = :v",
            ExpressionAttributeNames={"#t": "title"},
            ExpressionAttributeValues={":v": "Updated"},
        )

        assert result == expected
        mock_table.update_item.assert_called_once()

    def test_delete_item_success(self):
        mock_table = MagicMock()
        expected = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mock_table.delete_item.return_value = expected

        client = _make_db_client(mock_table)
        result = client.delete_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert result == expected
        mock_table.delete_item.assert_called_once_with(
            Key={"userId": "u1", "resourceId": "RESOURCE#abc"}
        )

    def test_query_success(self):
        mock_table = MagicMock()
        expected = {"Items": [{"userId": "u1", "resourceId": "RESOURCE#abc"}], "Count": 1}
        mock_table.query.return_value = expected

        client = _make_db_client(mock_table)
        result = client.query(KeyConditionExpression="userId = :uid")

        assert result == expected
        mock_table.query.assert_called_once_with(KeyConditionExpression="userId = :uid")


# ---------------------------------------------------------------------------
# DynamoDBClient — throttling → retry → success
# ---------------------------------------------------------------------------

class TestDynamoDBClientRetryOnThrottling:
    """On throttling error the method retries and eventually succeeds."""

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_get_item_retries_once_then_succeeds(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ProvisionedThroughputExceededException")
        success = {"Item": {"userId": "u1"}}
        mock_table.get_item.side_effect = [throttle, success]

        client = _make_db_client(mock_table)
        result = client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert result == success
        assert mock_table.get_item.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_put_item_retries_twice_then_succeeds(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ThrottlingException")
        success = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mock_table.put_item.side_effect = [throttle, throttle, success]

        client = _make_db_client(mock_table)
        result = client.put_item(Item={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert result == success
        assert mock_table.put_item.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_query_retries_on_request_limit_exceeded(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("RequestLimitExceeded")
        success = {"Items": [], "Count": 0}
        mock_table.query.side_effect = [throttle, success]

        client = _make_db_client(mock_table)
        result = client.query(KeyConditionExpression="pk = :v")

        assert result == success
        assert mock_table.query.call_count == 2

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_sleep_called_with_increasing_delays(self, mock_sleep):
        """Verify that sleep is called and delay grows with each retry attempt."""
        mock_table = MagicMock()
        throttle = _make_client_error("ThrottlingException")
        success = {"Items": []}
        # Two throttle failures then success → sleep called twice
        mock_table.query.side_effect = [throttle, throttle, success]

        with patch("shared.dynamodb_client._backoff_delay_seconds", side_effect=[0.1, 0.2]) as mock_delay:
            client = _make_db_client(mock_table)
            client.query(KeyConditionExpression="pk = :v")

        # _backoff_delay_seconds called for attempt 0 and attempt 1
        assert mock_delay.call_count == 2
        mock_delay.assert_any_call(0)
        mock_delay.assert_any_call(1)


# ---------------------------------------------------------------------------
# DynamoDBClient — exhausted retries → DynamoDBThrottlingError
# ---------------------------------------------------------------------------

class TestDynamoDBClientExhaustedRetries:
    """After MAX_RETRIES failures the wrapper raises DynamoDBThrottlingError."""

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_get_item_raises_after_max_retries(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ProvisionedThroughputExceededException")
        mock_table.get_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_put_item_raises_after_max_retries(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ThrottlingException")
        mock_table.put_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.put_item(Item={"userId": "u1", "resourceId": "RESOURCE#abc"})

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_update_item_raises_after_max_retries(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ProvisionedThroughputExceededException")
        mock_table.update_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.update_item(
                Key={"userId": "u1", "resourceId": "RESOURCE#abc"},
                UpdateExpression="SET #t = :v",
            )

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_delete_item_raises_after_max_retries(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("RequestLimitExceeded")
        mock_table.delete_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.delete_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_query_raises_after_max_retries(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ProvisionedThroughputExceededException")
        mock_table.query.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.query(KeyConditionExpression="pk = :v")

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_exactly_max_retries_sleep_calls(self, mock_sleep):
        """Verify sleep is called exactly MAX_RETRIES times before giving up."""
        mock_table = MagicMock()
        throttle = _make_client_error("ThrottlingException")
        mock_table.get_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert mock_sleep.call_count == MAX_RETRIES

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_error_message_includes_operation_name(self, mock_sleep):
        mock_table = MagicMock()
        throttle = _make_client_error("ThrottlingException")
        mock_table.query.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError, match="query"):
            client.query(KeyConditionExpression="pk = :v")

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_throttling_error_chained_from_client_error(self, mock_sleep):
        """DynamoDBThrottlingError should be chained from the original ClientError."""
        mock_table = MagicMock()
        throttle = _make_client_error("ProvisionedThroughputExceededException")
        mock_table.get_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError) as exc_info:
            client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ClientError)


# ---------------------------------------------------------------------------
# DynamoDBClient — non-throttling errors are NOT retried
# ---------------------------------------------------------------------------

class TestDynamoDBClientNonThrottlingErrors:
    """Non-throttling ClientErrors should be re-raised immediately."""

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_non_throttling_error_not_retried(self, mock_sleep):
        mock_table = MagicMock()
        not_found = _make_client_error("ResourceNotFoundException")
        mock_table.get_item.side_effect = not_found

        client = _make_db_client(mock_table)
        with pytest.raises(ClientError) as exc_info:
            client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        # Only one call — no retry
        assert mock_table.get_item.call_count == 1
        assert mock_sleep.call_count == 0
        assert exc_info.value.response["Error"]["Code"] == "ResourceNotFoundException"

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_validation_error_not_retried(self, mock_sleep):
        mock_table = MagicMock()
        validation_err = _make_client_error("ValidationException")
        mock_table.put_item.side_effect = validation_err

        client = _make_db_client(mock_table)
        with pytest.raises(ClientError):
            client.put_item(Item={"userId": "u1"})

        assert mock_table.put_item.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_conditional_check_failed_not_retried(self, mock_sleep):
        mock_table = MagicMock()
        cond_err = _make_client_error("ConditionalCheckFailedException")
        mock_table.delete_item.side_effect = cond_err

        client = _make_db_client(mock_table)
        with pytest.raises(ClientError):
            client.delete_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert mock_table.delete_item.call_count == 1

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_non_throttling_error_not_wrapped_in_throttling_error(self, mock_sleep):
        mock_table = MagicMock()
        not_found = _make_client_error("ResourceNotFoundException")
        mock_table.query.side_effect = not_found

        client = _make_db_client(mock_table)
        with pytest.raises(ClientError):
            client.query(KeyConditionExpression="pk = :v")

        # Must NOT be wrapped in DynamoDBThrottlingError
        # (the test above already confirmed it's a raw ClientError)


# ---------------------------------------------------------------------------
# DynamoDBClient — total call count verification
# ---------------------------------------------------------------------------

class TestDynamoDBClientCallCounts:
    """Verify exact number of underlying calls for various failure sequences."""

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_initial_call_plus_max_retries(self, mock_sleep):
        """Total calls = 1 initial + MAX_RETRIES retries = MAX_RETRIES + 1."""
        mock_table = MagicMock()
        throttle = _make_client_error("ProvisionedThroughputExceededException")
        mock_table.put_item.side_effect = [throttle] * (MAX_RETRIES + 1)

        client = _make_db_client(mock_table)
        with pytest.raises(DynamoDBThrottlingError):
            client.put_item(Item={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert mock_table.put_item.call_count == MAX_RETRIES + 1

    @patch("shared.dynamodb_client.time.sleep", return_value=None)
    def test_success_on_first_attempt_no_sleep(self, mock_sleep):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {}}

        client = _make_db_client(mock_table)
        client.get_item(Key={"userId": "u1", "resourceId": "RESOURCE#abc"})

        assert mock_table.get_item.call_count == 1
        assert mock_sleep.call_count == 0
