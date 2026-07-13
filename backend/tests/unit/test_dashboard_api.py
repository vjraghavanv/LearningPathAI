"""
Unit tests for DashboardAPI Lambda handler.

Covers specific examples, edge cases, and integration points including:
- No active Learning_Plan (Property 16 edge case — task 7.10)
- Today's task selection
- Completion percentage edge cases
- Study streak edge cases
- Parallel fetch happy path
- HTTP 401 for missing auth
- HTTP 503 on DynamoDB throttle

Requirements: 5.1–5.6, 12.1
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.dashboard_api.handler import (
    build_dashboard_response,
    compute_completion_percentage,
    compute_study_streak,
    compute_todays_task,
    handler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_event(user_id="user-123"):
    return {
        "httpMethod": "GET",
        "path": "/dashboard",
        "requestContext": {
            "requestId": "req-test",
            "authorizer": {"claims": {"sub": user_id}},
        },
        "body": None,
    }


def _make_plan(today="2026-07-12"):
    return {
        "userId": "user-123",
        "resourceId": "PLAN#active",
        "dailySchedule": [
            {
                "day": 1,
                "date": today,
                "resourceId": "RESOURCE#r1",
                "estimatedDuration": "1 hour",
                "recommendationReason": "Start with basics",
            }
        ],
        "weeklyRoadmap": ["Week 1: AWS Fundamentals"],
        "recommendedProjects": ["Build a serverless app"],
        "certificationRecommendations": ["AWS SAA"],
        "estimatedCompletionTimeline": "3 months",
        "resourcePriorityScores": {"RESOURCE#r1": 90},
    }


def _make_resources():
    return [
        {"resourceId": "RESOURCE#r1", "learningStatus": "Not Started", "title": "AWS IAM"},
        {"resourceId": "RESOURCE#r2", "learningStatus": "Completed", "title": "AWS S3"},
        {"resourceId": "RESOURCE#r3", "learningStatus": "Skipped", "title": "AWS SQS"},
    ]


def _make_streak(current=3):
    return {
        "userId": "user-123",
        "resourceId": "STREAK#current",
        "currentStreak": current,
        "lastCompletionDate": "2026-07-11",
    }


# ---------------------------------------------------------------------------
# Task 7.10: No-plan edge case (Property 16 edge case)
# ---------------------------------------------------------------------------

class TestNoPlanFallback:
    """Requirement 5.6: Return null plan-dependent fields with prompt when no active plan."""

    def test_no_plan_returns_null_learning_plan(self):
        response = build_dashboard_response("u1", None, [], None)
        assert response["learningPlan"] is None

    def test_no_plan_returns_null_todays_task(self):
        response = build_dashboard_response("u1", None, [], None)
        assert response["todaysTask"] is None

    def test_no_plan_returns_prompt_message(self):
        response = build_dashboard_response("u1", None, [], None)
        assert response["message"] is not None
        assert isinstance(response["message"], str)
        assert len(response["message"]) > 0

    def test_no_plan_returns_empty_lists_for_plan_fields(self):
        response = build_dashboard_response("u1", None, [], None)
        assert response["weeklyRoadmap"] == []
        assert response["certificationRecommendations"] == []
        assert response["recommendedProjects"] == []

    def test_no_plan_still_computes_completion_percentage(self):
        resources = _make_resources()
        response = build_dashboard_response("u1", None, resources, None)
        # 1 completed, 2 non-skipped → 50.0%
        assert response["completionPercentage"] == 50.0

    def test_no_plan_still_returns_streak(self):
        response = build_dashboard_response("u1", None, [], _make_streak(5))
        assert response["studyStreak"] == 5

    def test_handler_no_plan_returns_200(self):
        event = _make_event()
        with patch("lambdas.dashboard_api.handler.DynamoDBClient") as MockDB:
            db = MagicMock()
            db.get_item.return_value = {}           # no plan, no streak
            db.query.return_value = {"Items": []}  # no resources
            MockDB.return_value = db

            result = handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["learningPlan"] is None
        assert body["message"] is not None


# ---------------------------------------------------------------------------
# Today's task computation
# ---------------------------------------------------------------------------

class TestTodaysTask:
    def test_matching_date_returns_entry(self):
        plan = _make_plan("2026-07-12")
        entry = compute_todays_task(plan, "2026-07-12")
        assert entry is not None
        assert entry["resourceId"] == "RESOURCE#r1"

    def test_no_matching_date_returns_none(self):
        plan = _make_plan("2026-07-11")  # yesterday
        entry = compute_todays_task(plan, "2026-07-12")
        assert entry is None

    def test_none_plan_returns_none(self):
        assert compute_todays_task(None, "2026-07-12") is None

    def test_empty_schedule_returns_none(self):
        plan = {"dailySchedule": [], "userId": "u1", "resourceId": "PLAN#active"}
        assert compute_todays_task(plan, "2026-07-12") is None


# ---------------------------------------------------------------------------
# Completion percentage
# ---------------------------------------------------------------------------

class TestCompletionPercentage:
    def test_zero_percent_no_completed(self):
        resources = [
            {"learningStatus": "Not Started"},
            {"learningStatus": "In Progress"},
        ]
        assert compute_completion_percentage(resources) == 0.0

    def test_100_percent_all_completed(self):
        resources = [{"learningStatus": "Completed"}, {"learningStatus": "Completed"}]
        assert compute_completion_percentage(resources) == 100.0

    def test_50_percent(self):
        resources = [{"learningStatus": "Completed"}, {"learningStatus": "Not Started"}]
        assert compute_completion_percentage(resources) == 50.0

    def test_skipped_excluded_from_denominator(self):
        # 1 completed, 1 not-started, 2 skipped → 1/2 * 100 = 50.0
        resources = [
            {"learningStatus": "Completed"},
            {"learningStatus": "Not Started"},
            {"learningStatus": "Skipped"},
            {"learningStatus": "Skipped"},
        ]
        assert compute_completion_percentage(resources) == 50.0

    def test_all_skipped_returns_zero(self):
        resources = [{"learningStatus": "Skipped"}, {"learningStatus": "Skipped"}]
        assert compute_completion_percentage(resources) == 0.0

    def test_empty_returns_zero(self):
        assert compute_completion_percentage([]) == 0.0

    def test_rounds_to_one_decimal(self):
        # 1 of 3 → 33.333...% → 33.3%
        resources = [
            {"learningStatus": "Completed"},
            {"learningStatus": "Not Started"},
            {"learningStatus": "Not Started"},
        ]
        assert compute_completion_percentage(resources) == 33.3


# ---------------------------------------------------------------------------
# Study streak
# ---------------------------------------------------------------------------

class TestStudyStreak:
    def test_returns_stored_streak(self):
        assert compute_study_streak(_make_streak(7)) == 7

    def test_zero_streak(self):
        assert compute_study_streak(_make_streak(0)) == 0

    def test_none_record_returns_zero(self):
        assert compute_study_streak(None) == 0


# ---------------------------------------------------------------------------
# Handler integration
# ---------------------------------------------------------------------------

class TestHandler:
    def test_returns_200_with_plan(self):
        event = _make_event()
        today = "2026-07-12"
        with patch("lambdas.dashboard_api.handler.DynamoDBClient") as MockDB, \
             patch("lambdas.dashboard_api.handler._today_str", return_value=today):
            db = MagicMock()
            db.get_item.side_effect = [
                {"Item": _make_plan(today)},   # plan fetch
                {"Item": _make_streak(3)},     # streak fetch
            ]
            db.query.return_value = {"Items": _make_resources()}
            MockDB.return_value = db

            result = handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["learningPlan"] is not None
        assert body["studyStreak"] == 3

    def test_returns_401_without_auth(self):
        event = {
            "httpMethod": "GET",
            "path": "/dashboard",
            "requestContext": {},
            "body": None,
        }
        result = handler(event, None)
        assert result["statusCode"] == 401

    def test_returns_503_on_throttle(self):
        from shared.dynamodb_client import DynamoDBThrottlingError
        event = _make_event()
        with patch("lambdas.dashboard_api.handler.DynamoDBClient") as MockDB:
            db = MagicMock()
            db.get_item.side_effect = DynamoDBThrottlingError("throttled")
            MockDB.return_value = db

            result = handler(event, None)

        assert result["statusCode"] == 503
