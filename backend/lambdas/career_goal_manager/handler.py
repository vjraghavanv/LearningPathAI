"""
CareerGoalManager Lambda handler for LearningPath AI.

Routes:
  POST /career-goal — create/replace career goal profile (task 5.1)
  PUT  /career-goal — update career goal profile, trigger AI_Planner (task 5.2)

Validation (task 5.3):
  - careerGoal: predefined option or free-text ≤ 200 chars (required)
  - currentSkillLevel: Beginner | Intermediate | Advanced (required)
  - weeklyStudyHours: integer 1–168 (required)
  - preferredLearningPace: Slow | Moderate | Fast (optional)
  - Returns HTTP 400 on any validation failure

DynamoDB sort key: PROFILE#career_goal

Requirements: 3.1–3.8, 12.1, 12.2, 12.5
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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

CAREER_GOAL_SORT_KEY = "PROFILE#career_goal"

VALID_SKILL_LEVELS: frozenset[str] = frozenset({"Beginner", "Intermediate", "Advanced"})
VALID_PACES: frozenset[str] = frozenset({"Slow", "Moderate", "Fast"})
PREDEFINED_CAREER_GOALS: frozenset[str] = frozenset({
    "Become AWS Cloud Engineer",
    "Become DevOps Engineer",
    "Become AI Engineer",
    "Crack AWS SAA Certification",
    "Become Playwright Automation Expert",
})
MAX_CAREER_GOAL_LENGTH = 200
MIN_WEEKLY_HOURS = 1
MAX_WEEKLY_HOURS = 168


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_id(event: dict) -> str | None:
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
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


def _validation_error(message: str, field: str | None = None) -> dict:
    body: dict = {"error": "VALIDATION_ERROR", "message": message}
    if field:
        body["field"] = field
    return api_response(400, body)


# ---------------------------------------------------------------------------
# Validation (task 5.3)
# ---------------------------------------------------------------------------

def validate_career_goal_profile(body: dict) -> dict | None:
    """
    Validate career goal profile fields.
    Returns an error response dict on failure, or None if valid.
    """
    # Required: careerGoal
    career_goal = body.get("careerGoal")
    if not career_goal:
        return _validation_error("Required field 'careerGoal' is missing or empty.", field="careerGoal")
    if not isinstance(career_goal, str) or len(career_goal) > MAX_CAREER_GOAL_LENGTH:
        return _validation_error(
            f"'careerGoal' must be a string of at most {MAX_CAREER_GOAL_LENGTH} characters.",
            field="careerGoal",
        )

    # Required: currentSkillLevel
    skill_level = body.get("currentSkillLevel")
    if not skill_level:
        return _validation_error("Required field 'currentSkillLevel' is missing.", field="currentSkillLevel")
    if skill_level not in VALID_SKILL_LEVELS:
        return _validation_error(
            f"Invalid 'currentSkillLevel' '{skill_level}'. Must be one of: {', '.join(sorted(VALID_SKILL_LEVELS))}.",
            field="currentSkillLevel",
        )

    # Required: weeklyStudyHours
    hours = body.get("weeklyStudyHours")
    if hours is None:
        return _validation_error("Required field 'weeklyStudyHours' is missing.", field="weeklyStudyHours")
    try:
        hours_int = int(hours)
    except (TypeError, ValueError):
        return _validation_error("'weeklyStudyHours' must be an integer.", field="weeklyStudyHours")
    if not (MIN_WEEKLY_HOURS <= hours_int <= MAX_WEEKLY_HOURS):
        return _validation_error(
            f"'weeklyStudyHours' must be between {MIN_WEEKLY_HOURS} and {MAX_WEEKLY_HOURS}.",
            field="weeklyStudyHours",
        )

    # Optional: preferredLearningPace
    pace = body.get("preferredLearningPace")
    if pace and pace not in VALID_PACES:
        return _validation_error(
            f"Invalid 'preferredLearningPace' '{pace}'. Must be one of: {', '.join(sorted(VALID_PACES))}.",
            field="preferredLearningPace",
        )

    return None  # valid


# ---------------------------------------------------------------------------
# POST /career-goal (task 5.1)
# ---------------------------------------------------------------------------

def _handle_post(user_id: str, body: dict, db: DynamoDBClient) -> dict:
    error = validate_career_goal_profile(body)
    if error:
        return error

    now = _now_iso()
    item = {
        "userId": user_id,
        "resourceId": CAREER_GOAL_SORT_KEY,
        "careerGoal": body["careerGoal"],
        "currentSkillLevel": body["currentSkillLevel"],
        "weeklyStudyHours": int(body["weeklyStudyHours"]),
        "targetCompletionDate": body.get("targetCompletionDate"),
        "preferredLearningPace": body.get("preferredLearningPace", "Moderate"),
        "createdAt": now,
        "updatedAt": now,
    }
    db.put_item(Item=item)
    return api_response(201, item)


# ---------------------------------------------------------------------------
# PUT /career-goal (task 5.2)
# ---------------------------------------------------------------------------

def _handle_put(user_id: str, body: dict, db: DynamoDBClient, lambda_client: Any) -> dict:
    error = validate_career_goal_profile(body)
    if error:
        return error

    # Fetch existing to preserve createdAt
    resp = db.get_item(Key={"userId": user_id, "resourceId": CAREER_GOAL_SORT_KEY})
    existing = resp.get("Item") or {}

    now = _now_iso()
    item = {
        "userId": user_id,
        "resourceId": CAREER_GOAL_SORT_KEY,
        "careerGoal": body["careerGoal"],
        "currentSkillLevel": body["currentSkillLevel"],
        "weeklyStudyHours": int(body["weeklyStudyHours"]),
        "targetCompletionDate": body.get("targetCompletionDate", existing.get("targetCompletionDate")),
        "preferredLearningPace": body.get("preferredLearningPace", existing.get("preferredLearningPace", "Moderate")),
        "createdAt": existing.get("createdAt", now),
        "updatedAt": now,
    }
    db.put_item(Item=item)

    # Trigger AI_Planner asynchronously (Requirement 3.8)
    if AI_PLANNER_FUNCTION_NAME and lambda_client is not None:
        try:
            lambda_client.invoke(
                FunctionName=AI_PLANNER_FUNCTION_NAME,
                InvocationType="Event",
                Payload=json.dumps({"userId": user_id}).encode(),
            )
        except Exception:
            pass  # Non-fatal

    return api_response(200, item)


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
        http_method = (event.get("httpMethod") or "").upper()
        body = _parse_body(event)
        db = DynamoDBClient(table_name=TABLE_NAME)
        lambda_client = boto3.client("lambda") if AI_PLANNER_FUNCTION_NAME else None

        try:
            if http_method == "POST":
                result = _handle_post(user_id, body, db)
            elif http_method == "PUT":
                result = _handle_put(user_id, body, db, lambda_client)
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
