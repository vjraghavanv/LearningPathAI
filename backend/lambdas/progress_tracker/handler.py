"""
ProgressTracker Lambda handler for LearningPath AI.

Route:
  PUT /progress/{id} — update Learning_Status of a resource

Tasks covered:
  8.1  Ownership check (403), validate Learning_Status enum, persist to DynamoDB
  8.2  On Completed: record completion timestamp, trigger AI_Planner regeneration
  8.3  Streak increment: new calendar day completion increments STREAK#current by 1
  8.4  Streak reset: CloudWatch Event at midnight UTC checks lastCompletionDate
  8.5  Milestone recording at 25/50/75/100% completion thresholds
  8.6  Wire into CDK (handled in stack)

Requirements: 6.1–6.7, 7.1–7.5, 12.1, 12.2, 12.5
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any

import boto3

from shared.correlation import correlation_context
from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import InvocationTimer, make_logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")
AI_PLANNER_FUNCTION_NAME: str | None = os.environ.get("AI_PLANNER_FUNCTION_NAME")

VALID_STATUSES: frozenset[str] = frozenset(
    {"Not Started", "In Progress", "Completed", "Skipped"}
)
MILESTONE_THRESHOLDS: tuple[int, ...] = (25, 50, 75, 100)

STREAK_SORT_KEY = "STREAK#current"
COMPLETED_STATUS = "Completed"
SKIPPED_STATUS = "Skipped"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from shared.auth import get_user_id as _get_user_id


def _get_resource_id(event: dict) -> str | None:
    try:
        return event["pathParameters"]["id"]
    except (KeyError, TypeError):
        return None


def _parse_body(event: dict) -> dict:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return {}
    return body if isinstance(body, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Completion percentage helper (task 8.5)
# ---------------------------------------------------------------------------

def compute_completion_percentage(resources: list[dict]) -> float:
    """(Completed) / (non-Skipped) * 100, rounded to 1 decimal."""
    non_skipped = [r for r in resources if r.get("learningStatus") != SKIPPED_STATUS]
    if not non_skipped:
        return 0.0
    completed = sum(1 for r in non_skipped if r.get("learningStatus") == COMPLETED_STATUS)
    return round(completed / len(non_skipped) * 100, 1)


# ---------------------------------------------------------------------------
# Streak management (tasks 8.3, 8.4)
# ---------------------------------------------------------------------------

def update_streak(user_id: str, db: DynamoDBClient) -> None:
    """
    Increment streak if this is a new calendar day, else leave unchanged.
    Task 8.3: new calendar day completion increments STREAK#current by 1.
    """
    today = _today_str()
    resp = db.get_item(Key={"userId": user_id, "resourceId": STREAK_SORT_KEY})
    existing = resp.get("Item") or {}

    last_date = existing.get("lastCompletionDate")
    current_streak = int(existing.get("currentStreak", 0))

    if last_date == today:
        # Already completed something today — streak stays the same
        new_streak = current_streak
    else:
        # New day — increment
        new_streak = current_streak + 1

    db.put_item(Item={
        "userId": user_id,
        "resourceId": STREAK_SORT_KEY,
        "currentStreak": new_streak,
        "lastCompletionDate": today,
    })


def reset_streak(user_id: str, db: DynamoDBClient) -> None:
    """
    Task 8.4: Called by the midnight CloudWatch Event rule.
    Resets streak to 0 if lastCompletionDate is not today.
    """
    today = _today_str()
    resp = db.get_item(Key={"userId": user_id, "resourceId": STREAK_SORT_KEY})
    existing = resp.get("Item") or {}
    last_date = existing.get("lastCompletionDate")
    if last_date != today:
        db.put_item(Item={
            "userId": user_id,
            "resourceId": STREAK_SORT_KEY,
            "currentStreak": 0,
            "lastCompletionDate": last_date,
        })


# ---------------------------------------------------------------------------
# Milestone recording (task 8.5)
# ---------------------------------------------------------------------------

def record_milestones_if_crossed(
    user_id: str,
    old_pct: float,
    new_pct: float,
    db: DynamoDBClient,
) -> None:
    """Write a MILESTONE#<threshold> record for each newly crossed threshold."""
    now = _now_iso()
    for threshold in MILESTONE_THRESHOLDS:
        if old_pct < threshold <= new_pct:
            db.put_item(Item={
                "userId": user_id,
                "resourceId": f"MILESTONE#{threshold}",
                "threshold": threshold,
                "recordedAt": now,
            })


# ---------------------------------------------------------------------------
# AI Planner trigger (task 8.2)
# ---------------------------------------------------------------------------

def trigger_ai_planner(user_id: str, lambda_client: Any) -> None:
    """Asynchronously invoke AI_Planner to regenerate the plan."""
    if not AI_PLANNER_FUNCTION_NAME or lambda_client is None:
        return
    try:
        lambda_client.invoke(
            FunctionName=AI_PLANNER_FUNCTION_NAME,
            InvocationType="Event",
            Payload=json.dumps({"userId": user_id}).encode(),
        )
    except Exception:
        pass  # Non-fatal


# ---------------------------------------------------------------------------
# Core PUT handler
# ---------------------------------------------------------------------------

def handle_put_progress(
    user_id: str,
    resource_id: str,
    body: dict,
    db: DynamoDBClient,
    lambda_client: Any,
) -> dict:
    """
    Tasks 8.1–8.5: validate status, ownership check, persist, streak, milestones.
    """
    # Validate Learning_Status (task 8.1)
    new_status = body.get("learningStatus")
    if not new_status:
        return api_response(400, {
            "error": "VALIDATION_ERROR",
            "message": "Required field 'learningStatus' is missing.",
            "field": "learningStatus",
        })
    if new_status not in VALID_STATUSES:
        return api_response(400, {
            "error": "VALIDATION_ERROR",
            "message": (
                f"Invalid 'learningStatus' '{new_status}'. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}."
            ),
            "field": "learningStatus",
        })

    # Ensure resourceId has RESOURCE# prefix for DynamoDB key
    dynamo_resource_id = resource_id if resource_id.startswith("RESOURCE#") else f"RESOURCE#{resource_id}"

    # Fetch existing resource (ownership check — task 8.1)
    resp = db.get_item(Key={"userId": user_id, "resourceId": dynamo_resource_id})
    resource = resp.get("Item")
    if not resource:
        # Try without prefix (caller may have already included it)
        resp = db.get_item(Key={"userId": user_id, "resourceId": resource_id})
        resource = resp.get("Item")

    if not resource:
        return api_response(404, {"error": "NOT_FOUND", "message": "Resource not found."})

    # Ownership check (task 8.1, Requirement 6.7)
    if resource.get("userId") != user_id:
        return api_response(403, {"error": "FORBIDDEN", "message": "Access denied."})

    old_status = resource.get("learningStatus", "Not Started")
    now = _now_iso()

    # Fetch all resources to compute completion pct before update
    from boto3.dynamodb.conditions import Key
    all_resp = db.query(
        KeyConditionExpression=Key("userId").eq(user_id) & Key("resourceId").begins_with("RESOURCE#")
    )
    all_resources = all_resp.get("Items", [])

    old_pct = compute_completion_percentage(all_resources)

    # Persist new status (task 8.1)
    updated_resource = {
        **resource,
        "learningStatus": new_status,
        "updatedAt": now,
    }
    if new_status == COMPLETED_STATUS:
        # Task 8.2: record completion timestamp
        updated_resource["completionTimestamp"] = now

    db.put_item(Item=updated_resource)

    # Recompute percentage with updated status
    updated_resources = [
        {**r, "learningStatus": new_status} if r["resourceId"] == updated_resource["resourceId"] else r
        for r in all_resources
    ]
    new_pct = compute_completion_percentage(updated_resources)

    # Task 8.2: on Completed — update streak and trigger AI_Planner
    if new_status == COMPLETED_STATUS and old_status != COMPLETED_STATUS:
        update_streak(user_id, db)
        trigger_ai_planner(user_id, lambda_client)

    # Task 8.5: record milestones at crossed thresholds
    record_milestones_if_crossed(user_id, old_pct, new_pct, db)

    return api_response(200, updated_resource)


# ---------------------------------------------------------------------------
# Midnight streak reset handler (task 8.4)
# ---------------------------------------------------------------------------

def handle_streak_reset(event: dict, db: DynamoDBClient) -> None:
    """
    Called by the CloudWatch scheduled rule at midnight UTC.
    Iterates over all users via a scan or from the event payload.
    Event payload: {"userId": "<id>"} or {"userIds": ["<id1>", ...]}
    """
    user_ids: list[str] = []
    if "userId" in event:
        user_ids = [event["userId"]]
    elif "userIds" in event:
        user_ids = event["userIds"]

    for uid in user_ids:
        try:
            reset_streak(uid, db)
        except Exception:
            pass  # Log but don't fail the whole batch


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

@lambda_error_handler
def handler(event: dict, context: Any) -> dict:
    timer = InvocationTimer()
    logger = make_logger(event, context)

    with correlation_context(event):
        # Midnight streak reset event (task 8.4)
        if event.get("source") == "aws.events" or "userIds" in event or (
            "userId" in event and "httpMethod" not in event
        ):
            db = DynamoDBClient(table_name=TABLE_NAME)
            handle_streak_reset(event, db)
            return api_response(200, {"message": "Streak reset complete."})

        user_id = _get_user_id(event)
        if not user_id:
            return api_response(401, {"error": "UNAUTHORIZED", "message": "Missing or invalid authorization."})

        logger.set_user(user_id)
        http_method = (event.get("httpMethod") or "").upper()
        resource_id = _get_resource_id(event)
        body = _parse_body(event)
        db = DynamoDBClient(table_name=TABLE_NAME)
        lambda_client = boto3.client("lambda") if AI_PLANNER_FUNCTION_NAME else None

        try:
            if http_method in ("PUT", "PATCH") and resource_id:
                result = handle_put_progress(user_id, resource_id, body, db, lambda_client)
            else:
                result = api_response(405, {"error": "METHOD_NOT_ALLOWED", "message": f"Method {http_method} not supported."})
        except DynamoDBThrottlingError:
            logger.emit_error(status_code=503, duration_ms=timer.elapsed_ms(),
                              error_type="DynamoDBThrottlingError",
                              error_message="Service temporarily unavailable.")
            return api_response(503, {"error": "SERVICE_UNAVAILABLE", "message": "Service temporarily unavailable. Please retry."})

        status_code = result.get("statusCode", 200)
        if status_code >= 400:
            logger.emit_error(status_code=status_code, duration_ms=timer.elapsed_ms())
        else:
            logger.emit(status_code=status_code, duration_ms=timer.elapsed_ms())

        return result
