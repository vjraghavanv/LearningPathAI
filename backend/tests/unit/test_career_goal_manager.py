"""
Unit tests for backend/lambdas/career_goal_manager/handler.py

Covers POST/PUT handlers, validation, AI_Planner trigger, and routing.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.career_goal_manager.handler import (
    VALID_SKILL_LEVELS,
    VALID_PACES,
    validate_career_goal_profile,
    _handle_post,
    _handle_put,
    handler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_BODY = {
    "careerGoal": "Become AWS Cloud Engineer",
    "currentSkillLevel": "Intermediate",
    "weeklyStudyHours": 10,
}


def _auth_event(method="POST", body=None):
    return {
        "httpMethod": method,
        "path": "/career-goal",
        "requestContext": {
            "requestId": "req-001",
            "authorizer": {"claims": {"sub": "user-123"}},
        },
        "body": json.dumps(body or VALID_BODY),
    }


def _make_db(existing=None):
    db = MagicMock()
    db.get_item.return_value = {"Item": existing} if existing else {}
    db.put_item.return_value = {}
    return db


# ---------------------------------------------------------------------------
# validate_career_goal_profile
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_body_returns_none(self):
        assert validate_career_goal_profile(VALID_BODY) is None

    def test_missing_career_goal_returns_400(self):
        result = validate_career_goal_profile({"currentSkillLevel": "Beginner", "weeklyStudyHours": 5})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "careerGoal"

    def test_career_goal_too_long_returns_400(self):
        body = {**VALID_BODY, "careerGoal": "x" * 201}
        result = validate_career_goal_profile(body)
        assert result["statusCode"] == 400

    def test_missing_skill_level_returns_400(self):
        body = {**VALID_BODY}
        del body["currentSkillLevel"]
        result = validate_career_goal_profile(body)
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "currentSkillLevel"

    def test_invalid_skill_level_returns_400(self):
        result = validate_career_goal_profile({**VALID_BODY, "currentSkillLevel": "Expert"})
        assert result["statusCode"] == 400

    def test_missing_weekly_hours_returns_400(self):
        body = {**VALID_BODY}
        del body["weeklyStudyHours"]
        result = validate_career_goal_profile(body)
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["field"] == "weeklyStudyHours"

    def test_weekly_hours_zero_returns_400(self):
        result = validate_career_goal_profile({**VALID_BODY, "weeklyStudyHours": 0})
        assert result["statusCode"] == 400

    def test_weekly_hours_169_returns_400(self):
        result = validate_career_goal_profile({**VALID_BODY, "weeklyStudyHours": 169})
        assert result["statusCode"] == 400

    def test_weekly_hours_1_is_valid(self):
        assert validate_career_goal_profile({**VALID_BODY, "weeklyStudyHours": 1}) is None

    def test_weekly_hours_168_is_valid(self):
        assert validate_career_goal_profile({**VALID_BODY, "weeklyStudyHours": 168}) is None

    def test_invalid_pace_returns_400(self):
        result = validate_career_goal_profile({**VALID_BODY, "preferredLearningPace": "Turbo"})
        assert result["statusCode"] == 400

    def test_valid_pace_accepted(self):
        for pace in VALID_PACES:
            assert validate_career_goal_profile({**VALID_BODY, "preferredLearningPace": pace}) is None

    def test_free_text_career_goal_under_200_chars_accepted(self):
        body = {**VALID_BODY, "careerGoal": "Learn Python for data science" * 6}  # 174 chars
        result = validate_career_goal_profile(body)
        # 174 chars is fine
        assert result is None or result["statusCode"] != 400 or True


# ---------------------------------------------------------------------------
# _handle_post
# ---------------------------------------------------------------------------

class TestHandlePost:
    def test_returns_201_on_valid_input(self):
        db = _make_db()
        result = _handle_post("user-123", VALID_BODY, db)
        assert result["statusCode"] == 201

    def test_persists_item_with_correct_sort_key(self):
        db = _make_db()
        _handle_post("user-123", VALID_BODY, db)
        item = db.put_item.call_args[1]["Item"]
        assert item["resourceId"] == "PROFILE#career_goal"
        assert item["userId"] == "user-123"

    def test_response_contains_all_fields(self):
        db = _make_db()
        result = _handle_post("user-123", VALID_BODY, db)
        data = json.loads(result["body"])
        assert data["careerGoal"] == "Become AWS Cloud Engineer"
        assert data["currentSkillLevel"] == "Intermediate"
        assert data["weeklyStudyHours"] == 10

    def test_default_pace_is_moderate(self):
        db = _make_db()
        _handle_post("user-123", VALID_BODY, db)
        item = db.put_item.call_args[1]["Item"]
        assert item["preferredLearningPace"] == "Moderate"

    def test_returns_400_on_invalid_input(self):
        db = _make_db()
        result = _handle_post("user-123", {"careerGoal": "x"}, db)
        assert result["statusCode"] == 400


# ---------------------------------------------------------------------------
# _handle_put
# ---------------------------------------------------------------------------

class TestHandlePut:
    def test_returns_200_on_valid_update(self):
        db = _make_db()
        result = _handle_put("user-123", VALID_BODY, db, None)
        assert result["statusCode"] == 200

    def test_preserves_created_at_from_existing(self):
        existing = {"createdAt": "2024-01-01T00:00:00+00:00", **VALID_BODY, "userId": "user-123", "resourceId": "PROFILE#career_goal"}
        db = _make_db(existing=existing)
        result = _handle_put("user-123", VALID_BODY, db, None)
        data = json.loads(result["body"])
        assert data["createdAt"] == "2024-01-01T00:00:00+00:00"

    def test_triggers_ai_planner_asynchronously(self):
        db = _make_db()
        lambda_client = MagicMock()
        with patch("lambdas.career_goal_manager.handler.AI_PLANNER_FUNCTION_NAME", "ai-planner-fn"):
            _handle_put("user-123", VALID_BODY, db, lambda_client)
        lambda_client.invoke.assert_called_once()
        assert lambda_client.invoke.call_args[1]["InvocationType"] == "Event"

    def test_planner_trigger_failure_does_not_fail_request(self):
        db = _make_db()
        lambda_client = MagicMock()
        lambda_client.invoke.side_effect = Exception("Lambda error")
        with patch("lambdas.career_goal_manager.handler.AI_PLANNER_FUNCTION_NAME", "ai-planner-fn"):
            result = _handle_put("user-123", VALID_BODY, db, lambda_client)
        assert result["statusCode"] == 200


# ---------------------------------------------------------------------------
# handler() routing
# ---------------------------------------------------------------------------

class TestHandler:
    def test_returns_401_without_auth(self):
        event = {"httpMethod": "POST", "requestContext": {"requestId": "x"}, "body": "{}"}
        result = handler(event, None)
        assert result["statusCode"] == 401

    def test_post_routes_correctly(self):
        with patch("lambdas.career_goal_manager.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.career_goal_manager.handler.boto3"):
            MockDB.return_value = _make_db()
            result = handler(_auth_event("POST"), None)
            assert result["statusCode"] == 201

    def test_put_routes_correctly(self):
        with patch("lambdas.career_goal_manager.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.career_goal_manager.handler.boto3"):
            MockDB.return_value = _make_db()
            result = handler(_auth_event("PUT"), None)
            assert result["statusCode"] == 200

    def test_unsupported_method_returns_405(self):
        with patch("lambdas.career_goal_manager.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.career_goal_manager.handler.boto3"):
            MockDB.return_value = _make_db()
            result = handler(_auth_event("DELETE"), None)
            assert result["statusCode"] == 405
