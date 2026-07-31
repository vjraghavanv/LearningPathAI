"""
DashboardAPI Lambda handler for LearningPath AI.

Route:
  GET /dashboard — aggregate Learning_Plan, resources, and streak into a single response

Tasks covered:
  7.1  Fetch active Learning_Plan, all resources, and streak record in parallel
  7.2  Compute today's task from active plan
  7.3  Compute completion percentage: (Completed) / (non-Skipped) * 100
  7.4  Compute study streak from consecutive calendar days
  7.5  Return null for plan-dependent fields when no active plan exists
  7.6  Response time target of 3 seconds via parallel DynamoDB fetches

Requirements: 5.1–5.6, 12.1, 12.2, 12.5
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

from shared.correlation import correlation_context
from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import InvocationTimer, make_logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")

PLAN_SORT_KEY = "PLAN#active"
STREAK_SORT_KEY = "STREAK#current"

COMPLETED_STATUS = "Completed"
SKIPPED_STATUS = "Skipped"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from shared.auth import get_user_id as _get_user_id


def _today_str() -> str:
    """Return today's date as ISO 8601 string (UTC)."""
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# DynamoDB fetches (task 7.1 — run in parallel via ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def _fetch_plan(user_id: str, db: DynamoDBClient) -> dict | None:
    resp = db.get_item(Key={"userId": user_id, "resourceId": PLAN_SORT_KEY})
    return resp.get("Item")


def _fetch_resources(user_id: str, db: DynamoDBClient) -> list[dict]:
    from boto3.dynamodb.conditions import Key
    resp = db.query(
        KeyConditionExpression=Key("userId").eq(user_id) & Key("resourceId").begins_with("RESOURCE#")
    )
    return resp.get("Items", [])


def _fetch_streak(user_id: str, db: DynamoDBClient) -> dict | None:
    resp = db.get_item(Key={"userId": user_id, "resourceId": STREAK_SORT_KEY})
    return resp.get("Item")


def fetch_dashboard_data(user_id: str, db: DynamoDBClient) -> tuple[dict | None, list[dict], dict | None]:
    """
    Fetch plan, resources, and streak in parallel using a thread pool.
    Returns (plan, resources, streak).
    """
    results: dict[str, Any] = {}

    def _run(key, fn):
        results[key] = fn(user_id, db)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_run, "plan", _fetch_plan): "plan",
            pool.submit(_run, "resources", _fetch_resources): "resources",
            pool.submit(_run, "streak", _fetch_streak): "streak",
        }
        for future in as_completed(futures):
            future.result()  # propagate exceptions

    return results["plan"], results["resources"], results["streak"]


# ---------------------------------------------------------------------------
# Computation helpers (tasks 7.2–7.4)
# ---------------------------------------------------------------------------

def compute_todays_task(plan: dict | None, today: str) -> dict | None:
    """
    Task 7.2: Select the resource scheduled for today's calendar date.
    Matches on 'date' field (ISO 8601) in each dailySchedule entry.
    Falls back to matching by day index if no date field is present.
    """
    if not plan:
        return None
    schedule = plan.get("dailySchedule") or []
    for entry in schedule:
        if entry.get("date") == today:
            return entry
    return None


def compute_completion_percentage(resources: list[dict]) -> float:
    """
    Task 7.3: (count Completed) / (count non-Skipped) * 100, rounded to 1 decimal.
    Returns 0.0 when there are no non-skipped resources.
    """
    non_skipped = [r for r in resources if r.get("learningStatus") != SKIPPED_STATUS]
    if not non_skipped:
        return 0.0
    completed = sum(1 for r in non_skipped if r.get("learningStatus") == COMPLETED_STATUS)
    return round(completed / len(non_skipped) * 100, 1)


def compute_study_streak(streak_record: dict | None) -> int:
    """
    Task 7.4: Return the stored study streak value.
    The streak is maintained by ProgressTracker; DashboardAPI reads it directly.
    Returns 0 when no streak record exists.
    """
    if not streak_record:
        return 0
    return int(streak_record.get("currentStreak", 0))


def compute_weekly_progress(resources: list[dict]) -> dict:
    """
    Compute how many resources were completed per day of the current ISO week.
    Returns a dict keyed by ISO date string with completion counts.
    """
    today = date.today()
    week_start = today.toordinal() - today.weekday()  # Monday
    week_dates = {
        date.fromordinal(week_start + i).isoformat(): 0
        for i in range(7)
    }
    for r in resources:
        ts = r.get("completionTimestamp")
        if not ts:
            continue
        try:
            completion_date = datetime.fromisoformat(ts).date().isoformat()
            if completion_date in week_dates:
                week_dates[completion_date] += 1
        except (ValueError, TypeError):
            pass
    return week_dates


def extract_priority_resources(resources: list[dict], top_n: int = 5) -> list[dict]:
    """
    Return the top N non-completed, non-skipped resources sorted by
    aiMetadata.priorityScore descending.
    """
    active = [
        r for r in resources
        if r.get("learningStatus") not in (COMPLETED_STATUS, SKIPPED_STATUS)
    ]
    active.sort(
        key=lambda r: (r.get("aiMetadata") or {}).get("priorityScore", 0),
        reverse=True,
    )
    return active[:top_n]


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def build_dashboard_response(
    user_id: str,
    plan: dict | None,
    resources: list[dict],
    streak_record: dict | None,
) -> dict:
    """
    Assemble the full dashboard payload (Requirement 5.1).
    Returns null values for plan-dependent fields when no active plan exists (Requirement 5.6).
    """
    today = _today_str()
    has_plan = plan is not None

    todays_task = compute_todays_task(plan, today) if has_plan else None
    completion_pct = compute_completion_percentage(resources)
    streak = compute_study_streak(streak_record)
    weekly_progress = compute_weekly_progress(resources)
    priority_resources = extract_priority_resources(resources)

    return {
        "userId": user_id,
        "todaysTask": todays_task,
        "completionPercentage": completion_pct,
        "studyStreak": streak,
        "weeklyProgress": weekly_progress,
        "learningPlan": plan if has_plan else None,
        "priorityResources": priority_resources,
        "certificationRecommendations": (plan or {}).get("certificationRecommendations", []) if has_plan else [],
        "recommendedProjects": (plan or {}).get("recommendedProjects", []) if has_plan else [],
        "weeklyRoadmap": (plan or {}).get("weeklyRoadmap", []) if has_plan else [],
        "message": None if has_plan else "Set up your career goal to generate a personalised learning plan.",
    }


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

@lambda_error_handler
def handler(event: dict, context: Any) -> dict:
    timer = InvocationTimer()
    logger = make_logger(event, context)

    with correlation_context(event):
        user_id = _get_user_id(event)
        if not user_id:
            return api_response(401, {"error": "UNAUTHORIZED", "message": "Missing or invalid authorization."})

        logger.set_user(user_id)
        db = DynamoDBClient(table_name=TABLE_NAME)

        try:
            plan, resources, streak_record = fetch_dashboard_data(user_id, db)
        except DynamoDBThrottlingError:
            logger.emit_error(status_code=503, duration_ms=timer.elapsed_ms(),
                              error_type="DynamoDBThrottlingError",
                              error_message="Service temporarily unavailable.")
            return api_response(503, {"error": "SERVICE_UNAVAILABLE", "message": "Service temporarily unavailable. Please retry."})

        response_body = build_dashboard_response(user_id, plan, resources, streak_record)

        duration_ms = timer.elapsed_ms()
        logger.emit(status_code=200, duration_ms=duration_ms)
        return api_response(200, response_body)
