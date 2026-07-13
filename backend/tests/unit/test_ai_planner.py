"""
Unit tests for backend/lambdas/ai_planner/handler.py

Covers: fetch helpers, prompt builder, plan construction,
Bedrock invocation, error handling, and the Lambda handler.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.ai_planner.handler import (
    EXCLUDED_STATUSES,
    _parse_duration_hours,
    _parse_plan_json,
    build_learning_plan,
    build_planner_prompt,
    fetch_active_resources,
    handler,
    invoke_bedrock_planner,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROFILE = {
    "userId": "user-1",
    "resourceId": "PROFILE#career_goal",
    "careerGoal": "Become AWS Cloud Engineer",
    "currentSkillLevel": "Intermediate",
    "weeklyStudyHours": 14,
    "preferredLearningPace": "Moderate",
}

RESOURCES = [
    {"userId": "user-1", "resourceId": "RESOURCE#r1", "title": "EC2 Intro", "resourceType": "Technical Article",
     "learningStatus": "Not Started", "difficulty": "Beginner", "technology": "AWS", "aiMetadata": {"priorityScore": 80}},
    {"userId": "user-1", "resourceId": "RESOURCE#r2", "title": "S3 Deep Dive", "resourceType": "Online Course",
     "learningStatus": "In Progress", "difficulty": "Intermediate", "technology": "AWS", "aiMetadata": None},
]

COMPLETED_RESOURCE = {
    "userId": "user-1", "resourceId": "RESOURCE#r3", "title": "Old Course",
    "learningStatus": "Completed", "technology": "AWS",
}
SKIPPED_RESOURCE = {
    "userId": "user-1", "resourceId": "RESOURCE#r4", "title": "Skipped",
    "learningStatus": "Skipped", "technology": "AWS",
}

RAW_BEDROCK_PLAN = {
    "dailySchedule": [
        {"day": i, "resourceId": "RESOURCE#r1", "estimatedDuration": "1 hour", "recommendationReason": f"Day {i}"}
        for i in range(1, 8)
    ],
    "weeklyRoadmap": ["Week 1: AWS basics"],
    "recommendedProjects": ["Build S3 static site"],
    "certificationRecommendations": ["AWS SAA"],
    "estimatedCompletionTimeline": "3 months",
    "resourcePriorityScores": {"RESOURCE#r1": 85, "RESOURCE#r2": 60},
}


def _make_bedrock_response(content: str) -> dict:
    body_mock = MagicMock()
    body_mock.read.return_value = json.dumps({
        "output": {"message": {"content": [{"type": "text", "text": content}]}}
    }).encode("utf-8")
    return {"body": body_mock}


def _make_db(profile=PROFILE, resources=None):
    db = MagicMock()
    all_resources = resources if resources is not None else RESOURCES

    def get_item(Key):
        if Key.get("resourceId") == "PROFILE#career_goal":
            return {"Item": profile} if profile else {}
        if Key.get("resourceId") == "PLAN#active":
            return {}
        return {}

    db.get_item.side_effect = get_item
    db.query.return_value = {"Items": all_resources}
    db.put_item.return_value = {}
    return db


def _auth_event():
    return {
        "httpMethod": "POST",
        "path": "/learning-plan",
        "requestContext": {
            "requestId": "req-001",
            "authorizer": {"claims": {"sub": "user-1"}},
        },
        "body": "{}",
    }


# ---------------------------------------------------------------------------
# fetch_active_resources
# ---------------------------------------------------------------------------

class TestFetchActiveResources:
    def test_excludes_completed_resources(self):
        db = MagicMock()
        db.query.return_value = {"Items": RESOURCES + [COMPLETED_RESOURCE]}
        result = fetch_active_resources("user-1", db)
        ids = [r["resourceId"] for r in result]
        assert "RESOURCE#r3" not in ids

    def test_excludes_skipped_resources(self):
        db = MagicMock()
        db.query.return_value = {"Items": RESOURCES + [SKIPPED_RESOURCE]}
        result = fetch_active_resources("user-1", db)
        ids = [r["resourceId"] for r in result]
        assert "RESOURCE#r4" not in ids

    def test_includes_not_started_and_in_progress(self):
        db = MagicMock()
        db.query.return_value = {"Items": RESOURCES}
        result = fetch_active_resources("user-1", db)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# build_planner_prompt
# ---------------------------------------------------------------------------

class TestBuildPlannerPrompt:
    def test_prompt_contains_career_goal(self):
        prompt = build_planner_prompt(PROFILE, RESOURCES)
        assert "Become AWS Cloud Engineer" in prompt

    def test_prompt_contains_weekly_hours(self):
        prompt = build_planner_prompt(PROFILE, RESOURCES)
        assert "14" in prompt

    def test_prompt_requests_at_least_7_days(self):
        prompt = build_planner_prompt(PROFILE, RESOURCES)
        assert "7" in prompt

    def test_prompt_mentions_daily_budget(self):
        prompt = build_planner_prompt(PROFILE, RESOURCES)
        assert "hours/day" in prompt or "daily" in prompt.lower()

    def test_prompt_includes_resource_titles(self):
        prompt = build_planner_prompt(PROFILE, RESOURCES)
        assert "EC2 Intro" in prompt

    def test_prompt_requests_json_response(self):
        prompt = build_planner_prompt(PROFILE, RESOURCES)
        assert "json" in prompt.lower() or "JSON" in prompt


# ---------------------------------------------------------------------------
# build_learning_plan
# ---------------------------------------------------------------------------

class TestBuildLearningPlan:
    def test_daily_schedule_has_at_least_7_days(self):
        plan = build_learning_plan("user-1", RAW_BEDROCK_PLAN, PROFILE, RESOURCES)
        assert len(plan["dailySchedule"]) >= 7

    def test_plan_contains_required_keys(self):
        plan = build_learning_plan("user-1", RAW_BEDROCK_PLAN, PROFILE, RESOURCES)
        for key in ("dailySchedule", "weeklyRoadmap", "recommendedProjects",
                    "certificationRecommendations", "estimatedCompletionTimeline"):
            assert key in plan

    def test_daily_budget_enforced(self):
        profile_low = {**PROFILE, "weeklyStudyHours": 7}  # 1 hr/day
        raw = {
            **RAW_BEDROCK_PLAN,
            "dailySchedule": [
                {"day": i, "resourceId": "RESOURCE#r1",
                 "estimatedDuration": "3 hours", "recommendationReason": "test"}
                for i in range(1, 8)
            ],
        }
        plan = build_learning_plan("user-1", raw, profile_low, RESOURCES)
        for entry in plan["dailySchedule"]:
            duration_h = _parse_duration_hours(entry["estimatedDuration"])
            assert duration_h <= 1.0 + 1e-9

    def test_priority_scores_clamped_to_0_100(self):
        raw = {**RAW_BEDROCK_PLAN, "resourcePriorityScores": {"RESOURCE#r1": 150, "RESOURCE#r2": -10}}
        plan = build_learning_plan("user-1", raw, PROFILE, RESOURCES)
        for score in plan["resourcePriorityScores"].values():
            assert 0 <= score <= 100

    def test_pads_to_7_days_if_fewer(self):
        raw = {**RAW_BEDROCK_PLAN, "dailySchedule": [
            {"day": 1, "resourceId": "RESOURCE#r1", "estimatedDuration": "1 hour", "recommendationReason": "day 1"}
        ]}
        plan = build_learning_plan("user-1", raw, PROFILE, RESOURCES)
        assert len(plan["dailySchedule"]) >= 7

    def test_includes_career_goal_snapshot(self):
        plan = build_learning_plan("user-1", RAW_BEDROCK_PLAN, PROFILE, RESOURCES)
        assert plan["careerGoalSnapshot"]["careerGoal"] == "Become AWS Cloud Engineer"

    def test_plan_sort_key_is_plan_active(self):
        plan = build_learning_plan("user-1", RAW_BEDROCK_PLAN, PROFILE, RESOURCES)
        assert plan["resourceId"] == "PLAN#active"


# ---------------------------------------------------------------------------
# _parse_duration_hours
# ---------------------------------------------------------------------------

class TestParseDurationHours:
    def test_parses_hours(self):
        assert _parse_duration_hours("2 hours") == pytest.approx(2.0)

    def test_parses_minutes(self):
        assert _parse_duration_hours("90 minutes") == pytest.approx(1.5)

    def test_parses_float_hours(self):
        assert _parse_duration_hours("1.5 hours") == pytest.approx(1.5)

    def test_defaults_to_1_on_unrecognized(self):
        assert _parse_duration_hours("unknown") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# invoke_bedrock_planner
# ---------------------------------------------------------------------------

class TestInvokeBedrockPlanner:
    def test_returns_parsed_plan_on_success(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.return_value = _make_bedrock_response(json.dumps(RAW_BEDROCK_PLAN))
        result = invoke_bedrock_planner("test prompt", bedrock_client)
        assert result is not None
        assert "dailySchedule" in result

    def test_returns_none_on_client_error(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "throttled"}}, "InvokeModel"
        )
        assert invoke_bedrock_planner("test", bedrock_client) is None

    def test_returns_none_on_non_json_response(self):
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.return_value = _make_bedrock_response("sorry, I cannot help")
        assert invoke_bedrock_planner("test", bedrock_client) is None


# ---------------------------------------------------------------------------
# handler()
# ---------------------------------------------------------------------------

class TestHandler:
    def test_returns_401_without_auth(self):
        event = {"httpMethod": "POST", "requestContext": {"requestId": "x"}, "body": "{}"}
        result = handler(event, None)
        assert result["statusCode"] == 401

    def test_returns_400_when_no_career_goal(self):
        with patch("lambdas.ai_planner.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_planner.handler.boto3"):
            db = _make_db(profile=None)
            MockDB.return_value = db
            result = handler(_auth_event(), None)
            assert result["statusCode"] == 400

    def test_returns_201_on_success(self):
        with patch("lambdas.ai_planner.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_planner.handler.boto3") as mock_boto3:
            db = _make_db()
            MockDB.return_value = db
            bedrock_client = MagicMock()
            bedrock_client.invoke_model.return_value = _make_bedrock_response(json.dumps(RAW_BEDROCK_PLAN))
            mock_boto3.client.return_value = bedrock_client
            result = handler(_auth_event(), None)
            assert result["statusCode"] == 201

    def test_returns_503_on_bedrock_failure_and_preserves_plan(self):
        with patch("lambdas.ai_planner.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_planner.handler.boto3") as mock_boto3:
            db = _make_db()
            MockDB.return_value = db
            bedrock_client = MagicMock()
            bedrock_client.invoke_model.side_effect = Exception("Bedrock down")
            mock_boto3.client.return_value = bedrock_client
            result = handler(_auth_event(), None)
            assert result["statusCode"] == 503
            # Plan must NOT have been overwritten
            db.put_item.assert_not_called()

    def test_persists_plan_to_dynamodb(self):
        with patch("lambdas.ai_planner.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.ai_planner.handler.boto3") as mock_boto3:
            db = _make_db()
            MockDB.return_value = db
            bedrock_client = MagicMock()
            bedrock_client.invoke_model.return_value = _make_bedrock_response(json.dumps(RAW_BEDROCK_PLAN))
            mock_boto3.client.return_value = bedrock_client
            handler(_auth_event(), None)
            db.put_item.assert_called_once()
            item = db.put_item.call_args[1]["Item"]
            assert item["resourceId"] == "PLAN#active"
