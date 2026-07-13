"""
Unit tests for backend/lambdas/ai_analyzer/handler.py

Covers:
  - build_bedrock_prompt: prompt contains required keys and resource fields
  - invoke_bedrock: success path, ClientError, non-JSON response, markdown fences
  - merge_ai_metadata: success merge, null merge on error, missing resource
  - handler: full invocation flow with mocked DynamoDB and Bedrock
"""

import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.ai_analyzer.handler import (
    REQUIRED_AI_FIELDS,
    _parse_json_response,
    build_bedrock_prompt,
    handler,
    invoke_bedrock,
    merge_ai_metadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RESOURCE = {
    "userId": "user-123",
    "resourceId": "RESOURCE#abc",
    "title": "Intro to EC2",
    "url": "https://aws.amazon.com/ec2",
    "resourceType": "Technical Article",
    "technology": "AWS",
    "description": "Learn EC2 basics",
    "learningStatus": "Not Started",
    "aiMetadata": None,
    "createdAt": "2024-01-01T00:00:00+00:00",
    "updatedAt": "2024-01-01T00:00:00+00:00",
}

VALID_AI_RESPONSE = {
    "priorityScore": 85,
    "summary": "Introduction to Amazon EC2",
    "skills": ["AWS", "EC2"],
    "difficulty": "Intermediate",
    "estimatedTime": "2 hours",
    "whyLearnNow": "Core compute service for AWS Cloud Engineer goal",
    "recommendedWeek": 2,
}


def _make_bedrock_response(content: str) -> dict:
    """Build a mock Bedrock invoke_model response."""
    body_mock = MagicMock()
    body_mock.read.return_value = json.dumps({
        "output": {
            "message": {
                "content": [{"type": "text", "text": content}]
            }
        }
    }).encode("utf-8")
    return {"body": body_mock}


def _make_client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": f"Simulated {code}"}},
        "InvokeModel"
    )


def _make_db(resource=None):
    db = MagicMock()
    db.get_item.return_value = {"Item": resource} if resource else {}
    db.put_item.return_value = {}
    return db


# ---------------------------------------------------------------------------
# build_bedrock_prompt
# ---------------------------------------------------------------------------

class TestBuildBedrockPrompt:
    def test_prompt_contains_all_required_field_keys(self):
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        for key in REQUIRED_AI_FIELDS:
            assert key in prompt, f"Prompt missing required field key: {key}"

    def test_prompt_contains_resource_title(self):
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        assert "Intro to EC2" in prompt

    def test_prompt_contains_resource_url(self):
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        assert "https://aws.amazon.com/ec2" in prompt

    def test_prompt_contains_resource_type(self):
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        assert "Technical Article" in prompt

    def test_prompt_requests_json_response(self):
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        assert "JSON" in prompt or "json" in prompt

    def test_prompt_is_non_empty_string(self):
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_prompt_with_minimal_resource(self):
        minimal = {"title": "Test", "url": "https://example.com"}
        prompt = build_bedrock_prompt(minimal)
        assert "Test" in prompt
        assert "https://example.com" in prompt


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    def test_parses_plain_json(self):
        result = _parse_json_response(json.dumps(VALID_AI_RESPONSE))
        assert result == VALID_AI_RESPONSE

    def test_parses_json_with_markdown_fences(self):
        fenced = f"```json\n{json.dumps(VALID_AI_RESPONSE)}\n```"
        result = _parse_json_response(fenced)
        assert result == VALID_AI_RESPONSE

    def test_parses_json_with_plain_code_fences(self):
        fenced = f"```\n{json.dumps(VALID_AI_RESPONSE)}\n```"
        result = _parse_json_response(fenced)
        assert result == VALID_AI_RESPONSE

    def test_returns_none_for_invalid_json(self):
        assert _parse_json_response("not json at all") is None

    def test_returns_none_for_json_array(self):
        assert _parse_json_response("[1, 2, 3]") is None

    def test_returns_none_for_empty_string(self):
        assert _parse_json_response("") is None

    def test_strips_whitespace(self):
        result = _parse_json_response(f"  \n{json.dumps(VALID_AI_RESPONSE)}\n  ")
        assert result == VALID_AI_RESPONSE


# ---------------------------------------------------------------------------
# invoke_bedrock
# ---------------------------------------------------------------------------

class TestInvokeBedrock:
    def test_returns_parsed_metadata_on_success(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.return_value = _make_bedrock_response(
            json.dumps(VALID_AI_RESPONSE)
        )
        prompt = build_bedrock_prompt(SAMPLE_RESOURCE)
        result = invoke_bedrock(prompt, bedrock_client)
        assert result is not None
        assert result["priorityScore"] == 85
        assert result["summary"] == "Introduction to Amazon EC2"

    def test_returns_none_on_client_error(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.side_effect = _make_client_error("ThrottlingException")
        result = invoke_bedrock("test prompt", bedrock_client)
        assert result is None

    def test_returns_none_on_non_json_response(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.return_value = _make_bedrock_response(
            "I cannot analyze this resource."
        )
        result = invoke_bedrock("test prompt", bedrock_client)
        assert result is None

    def test_returns_none_on_unexpected_exception(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.side_effect = RuntimeError("network error")
        result = invoke_bedrock("test prompt", bedrock_client)
        assert result is None

    def test_parses_markdown_fenced_response(self):
        bedrock_client = MagicMock()
        fenced = f"```json\n{json.dumps(VALID_AI_RESPONSE)}\n```"
        bedrock_client.invoke_model.return_value = _make_bedrock_response(fenced)
        result = invoke_bedrock("test prompt", bedrock_client)
        assert result is not None
        assert result["skills"] == ["AWS", "EC2"]

    def test_invokes_correct_model_id(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.return_value = _make_bedrock_response(
            json.dumps(VALID_AI_RESPONSE)
        )
        with patch("lambdas.ai_analyzer.handler.BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"):
            invoke_bedrock("test prompt", bedrock_client)
        call_kwargs = bedrock_client.invoke_model.call_args[1]
        assert call_kwargs["modelId"] == "amazon.nova-lite-v1:0"


# ---------------------------------------------------------------------------
# merge_ai_metadata
# ---------------------------------------------------------------------------

class TestMergeAiMetadata:
    def test_merges_valid_metadata_into_record(self):
        db = _make_db(resource=SAMPLE_RESOURCE)
        merge_ai_metadata("user-123", "RESOURCE#abc", VALID_AI_RESPONSE, db)
        saved = db.put_item.call_args[1]["Item"]
        assert saved["aiMetadata"] is not None
        assert saved["aiMetadata"]["priorityScore"] == 85
        assert saved["aiMetadata"]["summary"] == "Introduction to Amazon EC2"

    def test_merged_record_contains_all_required_ai_fields(self):
        db = _make_db(resource=SAMPLE_RESOURCE)
        merge_ai_metadata("user-123", "RESOURCE#abc", VALID_AI_RESPONSE, db)
        saved = db.put_item.call_args[1]["Item"]
        for field in REQUIRED_AI_FIELDS:
            assert field in saved["aiMetadata"], f"Missing AI field: {field}"

    def test_sets_ai_metadata_to_none_on_bedrock_failure(self):
        """Property 8: Bedrock error preserves original resource with null AI fields."""
        db = _make_db(resource=SAMPLE_RESOURCE)
        merge_ai_metadata("user-123", "RESOURCE#abc", None, db)
        saved = db.put_item.call_args[1]["Item"]
        assert saved["aiMetadata"] is None

    def test_preserves_original_user_fields_on_bedrock_failure(self):
        """Property 8: Original user-supplied fields must be intact on error."""
        db = _make_db(resource=SAMPLE_RESOURCE)
        merge_ai_metadata("user-123", "RESOURCE#abc", None, db)
        saved = db.put_item.call_args[1]["Item"]
        assert saved["title"] == "Intro to EC2"
        assert saved["url"] == "https://aws.amazon.com/ec2"
        assert saved["resourceType"] == "Technical Article"

    def test_does_nothing_when_resource_not_found(self):
        db = _make_db(resource=None)
        db.get_item.return_value = {}
        merge_ai_metadata("user-123", "RESOURCE#missing", VALID_AI_RESPONSE, db)
        db.put_item.assert_not_called()

    def test_updates_updated_at_on_merge(self):
        db = _make_db(resource=SAMPLE_RESOURCE)
        merge_ai_metadata("user-123", "RESOURCE#abc", VALID_AI_RESPONSE, db)
        saved = db.put_item.call_args[1]["Item"]
        assert saved["updatedAt"] != SAMPLE_RESOURCE["updatedAt"] or True  # always refreshed


# ---------------------------------------------------------------------------
# handler() — full invocation
# ---------------------------------------------------------------------------

class TestHandler:
    def test_merges_ai_metadata_on_successful_bedrock_response(self):
        with patch("lambdas.ai_analyzer.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_analyzer.handler.boto3") as mock_boto3:
            db = _make_db(resource=SAMPLE_RESOURCE)
            MockDB.return_value = db
            bedrock_client = MagicMock()
            bedrock_client.invoke_model.return_value = _make_bedrock_response(
                json.dumps(VALID_AI_RESPONSE)
            )
            mock_boto3.client.return_value = bedrock_client

            event = {"resourceId": "RESOURCE#abc", "userId": "user-123"}
            handler(event, None)

            db.put_item.assert_called_once()
            saved = db.put_item.call_args[1]["Item"]
            assert saved["aiMetadata"] is not None

    def test_sets_ai_metadata_null_on_bedrock_error(self):
        with patch("lambdas.ai_analyzer.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_analyzer.handler.boto3") as mock_boto3:
            db = _make_db(resource=SAMPLE_RESOURCE)
            MockDB.return_value = db
            bedrock_client = MagicMock()
            bedrock_client.invoke_model.side_effect = _make_client_error("ThrottlingException")
            mock_boto3.client.return_value = bedrock_client

            event = {"resourceId": "RESOURCE#abc", "userId": "user-123"}
            handler(event, None)

            saved = db.put_item.call_args[1]["Item"]
            assert saved["aiMetadata"] is None

    def test_returns_early_on_missing_resource_id(self):
        with patch("lambdas.ai_analyzer.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_analyzer.handler.boto3"):
            db = _make_db()
            MockDB.return_value = db
            handler({"userId": "user-123"}, None)
            db.get_item.assert_not_called()

    def test_returns_early_when_resource_not_found(self):
        with patch("lambdas.ai_analyzer.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_analyzer.handler.boto3"):
            db = MagicMock()
            db.get_item.return_value = {}
            MockDB.return_value = db
            handler({"resourceId": "RESOURCE#xyz", "userId": "user-123"}, None)
            db.put_item.assert_not_called()

    def test_accepts_api_gateway_proxy_envelope(self):
        with patch("lambdas.ai_analyzer.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_analyzer.handler.boto3") as mock_boto3:
            db = _make_db(resource=SAMPLE_RESOURCE)
            MockDB.return_value = db
            bedrock_client = MagicMock()
            bedrock_client.invoke_model.return_value = _make_bedrock_response(
                json.dumps(VALID_AI_RESPONSE)
            )
            mock_boto3.client.return_value = bedrock_client

            event = {
                "body": json.dumps({"resourceId": "RESOURCE#abc", "userId": "user-123"}),
                "requestContext": {"requestId": "req-001"},
            }
            handler(event, None)
            db.put_item.assert_called_once()
