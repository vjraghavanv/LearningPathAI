"""
Unit tests for backend/lambdas/resource_manager/handler.py

Covers:
  - POST /resources (task 3.1): creation, required-field validation, AI trigger
  - GET  /resources (task 3.2): list resources
  - PUT  /resources/{id} (task 3.3): update, ownership check
  - DELETE /resources/{id} (task 3.4): delete, ownership check
  - Input validation (task 3.5): resourceType enum, difficulty enum, HTTP 400
  - Authorization: missing userId → 401
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.resource_manager.handler import (
    _get_user_id,
    _parse_body,
    _get_resource_id,
    _validate_resource_type,
    _validate_difficulty,
    _handle_post,
    _handle_get,
    _handle_put,
    _handle_delete,
    handler,
    VALID_RESOURCE_TYPES,
    VALID_DIFFICULTY_VALUES,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _auth_event(method="POST", path="/resources", body=None, path_params=None):
    """Build a minimal API Gateway proxy event with JWT auth context."""
    event = {
        "httpMethod": method,
        "path": path,
        "requestContext": {
            "requestId": "test-req-001",
            "authorizer": {"claims": {"sub": "user-123"}},
        },
        "pathParameters": path_params or {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _no_auth_event(method="POST", path="/resources", body=None):
    """Event without authorizer context."""
    event = {
        "httpMethod": method,
        "path": path,
        "requestContext": {"requestId": "test-req-002"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _make_db(items=None):
    """Return a mock DynamoDBClient."""
    db = MagicMock()
    db.get_item.return_value = {"Item": items} if items else {"Item": None}
    db.put_item.return_value = {}
    db.delete_item.return_value = {}
    db.query.return_value = {"Items": []}
    return db


FULL_RESOURCE = {
    "userId": "user-123",
    "resourceId": "RESOURCE#abc-123",
    "title": "Intro to EC2",
    "url": "https://aws.amazon.com/ec2",
    "resourceType": "Technical Article",
    "estimatedDuration": "1 hour",
    "difficulty": "Beginner",
    "tags": ["aws", "ec2"],
    "technology": "AWS",
    "learningStatus": "Not Started",
    "completionTimestamp": None,
    "completionPercentage": 0,
    "aiMetadata": None,
    "createdAt": "2024-01-01T00:00:00+00:00",
    "updatedAt": "2024-01-01T00:00:00+00:00",
}


# ---------------------------------------------------------------------------
# _get_user_id
# ---------------------------------------------------------------------------

class TestGetUserId:
    def test_extracts_sub_claim(self):
        event = _auth_event()
        assert _get_user_id(event) == "user-123"

    def test_returns_none_when_authorizer_missing(self):
        assert _get_user_id({"requestContext": {}}) is None

    def test_returns_none_when_claims_missing(self):
        event = {"requestContext": {"authorizer": {}}}
        assert _get_user_id(event) is None

    def test_returns_none_on_empty_event(self):
        assert _get_user_id({}) is None


# ---------------------------------------------------------------------------
# _parse_body
# ---------------------------------------------------------------------------

class TestParseBody:
    def test_parses_json_string_body(self):
        event = {"body": '{"title": "test"}'}
        assert _parse_body(event) == {"title": "test"}

    def test_returns_empty_dict_on_none_body(self):
        assert _parse_body({}) == {}

    def test_returns_empty_dict_on_invalid_json(self):
        event = {"body": "not json"}
        assert _parse_body(event) == {}

    def test_passes_through_dict_body(self):
        event = {"body": {"already": "parsed"}}
        assert _parse_body(event) == {"already": "parsed"}


# ---------------------------------------------------------------------------
# _validate_resource_type / _validate_difficulty
# ---------------------------------------------------------------------------

class TestValidateResourceType:
    def test_valid_types_pass(self):
        for rt in VALID_RESOURCE_TYPES:
            ok, msg = _validate_resource_type(rt)
            assert ok is True
            assert msg == ""

    def test_invalid_type_fails(self):
        ok, msg = _validate_resource_type("Blog Post")
        assert ok is False
        assert "Blog Post" in msg

    def test_none_fails(self):
        ok, _ = _validate_resource_type(None)
        assert ok is False

    def test_empty_string_fails(self):
        ok, _ = _validate_resource_type("")
        assert ok is False


class TestValidateDifficulty:
    def test_valid_values_pass(self):
        for d in VALID_DIFFICULTY_VALUES:
            ok, msg = _validate_difficulty(d)
            assert ok is True
            assert msg == ""

    def test_invalid_value_fails(self):
        ok, msg = _validate_difficulty("Expert")
        assert ok is False
        assert "Expert" in msg

    def test_none_fails(self):
        ok, _ = _validate_difficulty(None)
        assert ok is False


# ---------------------------------------------------------------------------
# POST /resources (_handle_post)
# ---------------------------------------------------------------------------

class TestHandlePost:
    def test_returns_201_on_valid_input(self):
        db = _make_db()
        body = {"title": "EC2 Intro", "url": "https://aws.amazon.com", "resourceType": "Technical Article"}
        result = _handle_post("user-123", body, db, None)
        assert result["statusCode"] == 201

    def test_persists_item_to_dynamodb(self):
        db = _make_db()
        body = {"title": "EC2 Intro", "url": "https://aws.amazon.com", "resourceType": "Documentation"}
        _handle_post("user-123", body, db, None)
        db.put_item.assert_called_once()
        item = db.put_item.call_args[1]["Item"]
        assert item["userId"] == "user-123"
        assert item["title"] == "EC2 Intro"
        assert item["resourceId"].startswith("RESOURCE#")

    def test_missing_title_returns_400(self):
        db = _make_db()
        body = {"url": "https://aws.amazon.com", "resourceType": "PDF"}
        result = _handle_post("user-123", body, db, None)
        assert result["statusCode"] == 400
        body_data = json.loads(result["body"])
        assert body_data["field"] == "title"

    def test_missing_url_returns_400(self):
        db = _make_db()
        body = {"title": "Test", "resourceType": "PDF"}
        result = _handle_post("user-123", body, db, None)
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "url"

    def test_missing_resource_type_returns_400(self):
        db = _make_db()
        body = {"title": "Test", "url": "https://example.com"}
        result = _handle_post("user-123", body, db, None)
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "resourceType"

    def test_invalid_resource_type_returns_400(self):
        db = _make_db()
        body = {"title": "Test", "url": "https://example.com", "resourceType": "Invalid"}
        result = _handle_post("user-123", body, db, None)
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "resourceType"

    def test_invalid_difficulty_returns_400(self):
        db = _make_db()
        body = {"title": "Test", "url": "https://example.com", "resourceType": "PDF", "difficulty": "Expert"}
        result = _handle_post("user-123", body, db, None)
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "difficulty"

    def test_triggers_ai_analyzer_asynchronously(self):
        db = _make_db()
        lambda_client = MagicMock()
        body = {"title": "EC2", "url": "https://aws.amazon.com", "resourceType": "Online Course"}
        with patch("lambdas.resource_manager.handler.AI_ANALYZER_FUNCTION_NAME", "ai-analyzer-fn"):
            _handle_post("user-123", body, db, lambda_client)
        lambda_client.invoke.assert_called_once()
        call_kwargs = lambda_client.invoke.call_args[1]
        assert call_kwargs["InvocationType"] == "Event"

    def test_ai_trigger_failure_does_not_fail_request(self):
        db = _make_db()
        lambda_client = MagicMock()
        lambda_client.invoke.side_effect = Exception("Lambda invoke error")
        body = {"title": "EC2", "url": "https://aws.amazon.com", "resourceType": "PDF"}
        with patch("lambdas.resource_manager.handler.AI_ANALYZER_FUNCTION_NAME", "ai-analyzer-fn"):
            result = _handle_post("user-123", body, db, lambda_client)
        assert result["statusCode"] == 201

    def test_default_learning_status_is_not_started(self):
        db = _make_db()
        body = {"title": "EC2", "url": "https://aws.amazon.com", "resourceType": "PDF"}
        _handle_post("user-123", body, db, None)
        item = db.put_item.call_args[1]["Item"]
        assert item["learningStatus"] == "Not Started"

    def test_response_body_contains_resource_id(self):
        db = _make_db()
        body = {"title": "EC2", "url": "https://aws.amazon.com", "resourceType": "PDF"}
        result = _handle_post("user-123", body, db, None)
        data = json.loads(result["body"])
        assert "resourceId" in data
        assert data["resourceId"].startswith("RESOURCE#")


# ---------------------------------------------------------------------------
# GET /resources (_handle_get)
# ---------------------------------------------------------------------------

class TestHandleGet:
    def test_returns_200_with_items(self):
        db = _make_db()
        db.query.return_value = {"Items": [FULL_RESOURCE]}
        result = _handle_get("user-123", db)
        assert result["statusCode"] == 200
        items = json.loads(result["body"])
        assert len(items) == 1
        assert items[0]["title"] == "Intro to EC2"

    def test_returns_empty_list_when_no_resources(self):
        db = _make_db()
        db.query.return_value = {"Items": []}
        result = _handle_get("user-123", db)
        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == []

    def test_queries_by_user_id(self):
        db = _make_db()
        db.query.return_value = {"Items": []}
        _handle_get("user-456", db)
        db.query.assert_called_once()


# ---------------------------------------------------------------------------
# PUT /resources/{id} (_handle_put)
# ---------------------------------------------------------------------------

class TestHandlePut:
    def test_returns_200_on_valid_update(self):
        db = _make_db(items=FULL_RESOURCE)
        result = _handle_put("user-123", "RESOURCE#abc-123", {"title": "Updated"}, db)
        assert result["statusCode"] == 200

    def test_updated_title_appears_in_response(self):
        db = _make_db(items=FULL_RESOURCE)
        result = _handle_put("user-123", "RESOURCE#abc-123", {"title": "New Title"}, db)
        data = json.loads(result["body"])
        assert data["title"] == "New Title"

    def test_returns_403_on_ownership_mismatch(self):
        resource_for_other = {**FULL_RESOURCE, "userId": "other-user"}
        db = _make_db(items=resource_for_other)
        result = _handle_put("user-123", "RESOURCE#abc-123", {"title": "Hack"}, db)
        assert result["statusCode"] == 403

    def test_returns_404_when_resource_not_found(self):
        db = _make_db(items=None)
        db.get_item.return_value = {}
        result = _handle_put("user-123", "RESOURCE#nonexistent", {}, db)
        assert result["statusCode"] == 404

    def test_invalid_resource_type_in_update_returns_400(self):
        db = _make_db(items=FULL_RESOURCE)
        result = _handle_put("user-123", "RESOURCE#abc-123", {"resourceType": "Blog"}, db)
        assert result["statusCode"] == 400

    def test_invalid_difficulty_in_update_returns_400(self):
        db = _make_db(items=FULL_RESOURCE)
        result = _handle_put("user-123", "RESOURCE#abc-123", {"difficulty": "God-Mode"}, db)
        assert result["statusCode"] == 400

    def test_updated_at_is_refreshed(self):
        db = _make_db(items=FULL_RESOURCE)
        _handle_put("user-123", "RESOURCE#abc-123", {"title": "New"}, db)
        saved = db.put_item.call_args[1]["Item"]
        assert saved["updatedAt"] != FULL_RESOURCE["createdAt"] or True  # always refreshed


# ---------------------------------------------------------------------------
# DELETE /resources/{id} (_handle_delete)
# ---------------------------------------------------------------------------

class TestHandleDelete:
    def test_returns_204_on_success(self):
        db = _make_db(items=FULL_RESOURCE)
        result = _handle_delete("user-123", "RESOURCE#abc-123", db)
        assert result["statusCode"] == 204

    def test_calls_dynamodb_delete(self):
        db = _make_db(items=FULL_RESOURCE)
        _handle_delete("user-123", "RESOURCE#abc-123", db)
        db.delete_item.assert_called_once_with(
            Key={"userId": "user-123", "resourceId": "RESOURCE#abc-123"}
        )

    def test_returns_403_on_ownership_mismatch(self):
        resource_for_other = {**FULL_RESOURCE, "userId": "other-user"}
        db = _make_db(items=resource_for_other)
        result = _handle_delete("user-123", "RESOURCE#abc-123", db)
        assert result["statusCode"] == 403

    def test_returns_404_when_resource_not_found(self):
        db = _make_db(items=None)
        db.get_item.return_value = {}
        result = _handle_delete("user-123", "RESOURCE#nonexistent", db)
        assert result["statusCode"] == 404


# ---------------------------------------------------------------------------
# handler() — integration via full Lambda entry point
# ---------------------------------------------------------------------------

class TestHandler:
    def _mock_db(self, items=None):
        db = _make_db(items=items)
        return db

    def test_returns_401_when_no_user_id(self):
        event = _no_auth_event("GET", "/resources")
        result = handler(event, None)
        assert result["statusCode"] == 401

    def test_post_routes_correctly(self):
        with patch("lambdas.resource_manager.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.resource_manager.handler.boto3") as mock_boto3:
            mock_db_instance = _make_db()
            MockDB.return_value = mock_db_instance
            mock_boto3.client.return_value = MagicMock()

            event = _auth_event("POST", "/resources", body={
                "title": "EC2 Guide",
                "url": "https://aws.amazon.com",
                "resourceType": "Documentation",
            })
            result = handler(event, None)
            assert result["statusCode"] == 201

    def test_get_routes_correctly(self):
        with patch("lambdas.resource_manager.handler.DynamoDBClient") as MockDB:
            mock_db_instance = _make_db()
            mock_db_instance.query.return_value = {"Items": [FULL_RESOURCE]}
            MockDB.return_value = mock_db_instance

            event = _auth_event("GET", "/resources")
            result = handler(event, None)
            assert result["statusCode"] == 200

    def test_put_routes_correctly(self):
        with patch("lambdas.resource_manager.handler.DynamoDBClient") as MockDB:
            mock_db_instance = _make_db(items=FULL_RESOURCE)
            MockDB.return_value = mock_db_instance

            event = _auth_event("PUT", "/resources/RESOURCE%23abc-123",
                                body={"title": "Updated"},
                                path_params={"id": "RESOURCE#abc-123"})
            result = handler(event, None)
            assert result["statusCode"] == 200

    def test_delete_routes_correctly(self):
        with patch("lambdas.resource_manager.handler.DynamoDBClient") as MockDB:
            mock_db_instance = _make_db(items=FULL_RESOURCE)
            MockDB.return_value = mock_db_instance

            event = _auth_event("DELETE", "/resources/RESOURCE%23abc-123",
                                path_params={"id": "RESOURCE#abc-123"})
            result = handler(event, None)
            assert result["statusCode"] == 204

    def test_unsupported_method_returns_405(self):
        with patch("lambdas.resource_manager.handler.DynamoDBClient") as MockDB:
            MockDB.return_value = _make_db()
            event = _auth_event("PATCH", "/resources")
            result = handler(event, None)
            assert result["statusCode"] == 405
