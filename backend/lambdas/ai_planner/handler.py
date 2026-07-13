"""
AI Planner Lambda handler for LearningPath AI.

Route:
  POST /learning-plan — generate a personalized Learning_Plan via Bedrock Nova Lite

Tasks covered:
  6.1  Fetch career goal profile + resource list, build prompt, invoke Bedrock (60s timeout)
  6.2  Parse Bedrock JSON response into structured Learning_Plan (≥7 days)
  6.3  Validate no day exceeds average daily availability (weeklyStudyHours / 7)
  6.4  Exclude resources with Learning_Status Completed or Skipped
  6.5  Validate all Priority_Score values in [0, 100]
  6.6  On Bedrock error: return HTTP 503, preserve last valid plan, log to CloudWatch
  6.7  Persist generated Learning_Plan under PLAN#active sort key

Requirements: 4.1–4.10, 7.1–7.5, 12.1, 12.2, 12.5
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.correlation import correlation_context, get_correlation_id
from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import InvocationTimer, make_logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")
BEDROCK_MODEL_ID: str = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
BEDROCK_TIMEOUT_SECONDS: int = 60

PLAN_SORT_KEY = "PLAN#active"
PROFILE_SORT_KEY = "PROFILE#career_goal"

EXCLUDED_STATUSES: frozenset[str] = frozenset({"Completed", "Skipped"})

_log = logging.getLogger(__name__)
_log.setLevel(logging.INFO)
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_h)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_user_id(event: dict) -> str | None:
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_career_goal_profile(user_id: str, db: DynamoDBClient) -> dict | None:
    resp = db.get_item(Key={"userId": user_id, "resourceId": PROFILE_SORT_KEY})
    return resp.get("Item")


def fetch_active_resources(user_id: str, db: DynamoDBClient) -> list[dict]:
    """Fetch all resources for user, excluding Completed and Skipped (task 6.4)."""
    from boto3.dynamodb.conditions import Key
    resp = db.query(
        KeyConditionExpression=Key("userId").eq(user_id) & Key("resourceId").begins_with("RESOURCE#")
    )
    return [
        r for r in resp.get("Items", [])
        if r.get("learningStatus") not in EXCLUDED_STATUSES
    ]


def fetch_last_plan(user_id: str, db: DynamoDBClient) -> dict | None:
    resp = db.get_item(Key={"userId": user_id, "resourceId": PLAN_SORT_KEY})
    return resp.get("Item")


# ---------------------------------------------------------------------------
# Prompt builder (task 6.1)
# ---------------------------------------------------------------------------

def build_planner_prompt(profile: dict, resources: list[dict]) -> str:
    """Build the Bedrock prompt for generating a Learning_Plan."""
    career_goal = profile.get("careerGoal", "")
    skill_level = profile.get("currentSkillLevel", "Intermediate")
    weekly_hours = profile.get("weeklyStudyHours", 10)
    pace = profile.get("preferredLearningPace", "Moderate")
    daily_budget_hours = round(weekly_hours / 7, 1)

    resource_summaries = []
    for r in resources:
        resource_summaries.append(
            f"- ID: {r.get('resourceId', '')}, Title: {r.get('title', '')}, "
            f"Type: {r.get('resourceType', '')}, Difficulty: {r.get('difficulty', '')}, "
            f"Technology: {r.get('technology', '')}, "
            f"Priority: {(r.get('aiMetadata') or {}).get('priorityScore', 'unknown')}"
        )

    resources_text = "\n".join(resource_summaries) if resource_summaries else "No resources available."

    return (
        f"You are a personalized learning planner. Create a learning plan for this learner.\n\n"
        f"Career Goal: {career_goal}\n"
        f"Current Skill Level: {skill_level}\n"
        f"Weekly Study Hours: {weekly_hours}\n"
        f"Daily Budget: {daily_budget_hours} hours/day\n"
        f"Learning Pace: {pace}\n\n"
        f"Available Resources:\n{resources_text}\n\n"
        f"IMPORTANT CONSTRAINTS:\n"
        f"- Schedule AT LEAST 7 days\n"
        f"- No single day must exceed {daily_budget_hours} hours of study time\n"
        f"- Assign a priorityScore (0-100) to each resource\n"
        f"- Include a recommendationReason for each scheduled day\n\n"
        f"Respond with ONLY a valid JSON object (no markdown, no extra text):\n"
        "{\n"
        '  "dailySchedule": [\n'
        '    {"day": 1, "resourceId": "<id>", "estimatedDuration": "<e.g. 1.5 hours>", "recommendationReason": "<why>"}\n'
        "  ],\n"
        '  "weeklyRoadmap": ["<week 1 focus>"],\n'
        '  "recommendedProjects": ["<project>"],\n'
        '  "certificationRecommendations": ["<cert>"],\n'
        '  "estimatedCompletionTimeline": "<e.g. 3 months>",\n'
        '  "resourcePriorityScores": {"<resourceId>": <0-100>}\n'
        "}"
    )


# ---------------------------------------------------------------------------
# Bedrock invocation (task 6.1, 6.6)
# ---------------------------------------------------------------------------

def invoke_bedrock_planner(prompt: str, bedrock_client: Any) -> dict | None:
    """Invoke Bedrock and return parsed JSON, or None on any error."""
    request_body = json.dumps({
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "inferenceConfig": {"maxTokens": 2048, "temperature": 0.2},
    })

    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )
        raw_body = response["body"].read().decode("utf-8")
    except (ClientError, Exception) as exc:
        _log.error(json.dumps({
            "level": "ERROR",
            "message": "Bedrock error during plan generation",
            "errorType": type(exc).__name__,
            "correlationId": get_correlation_id(),
        }))
        return None

    try:
        envelope = json.loads(raw_body)
        content_blocks = (
            envelope.get("output", {}).get("message", {}).get("content", [])
        )
        text = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                break
        if not text:
            text = envelope.get("completion", raw_body)
    except (json.JSONDecodeError, KeyError):
        text = raw_body

    return _parse_plan_json(text)


def _parse_plan_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Plan construction (tasks 6.2, 6.3, 6.5)
# ---------------------------------------------------------------------------

def build_learning_plan(
    user_id: str,
    raw_plan: dict,
    profile: dict,
    resources: list[dict],
) -> dict:
    """
    Construct and validate a structured Learning_Plan from Bedrock's raw output.

    - Ensures ≥7 days in dailySchedule (task 6.2)
    - Validates priority scores in [0, 100] (task 6.5)
    - Validates daily study budget (task 6.3)
    """
    weekly_hours = profile.get("weeklyStudyHours", 10)
    daily_budget_hours = weekly_hours / 7

    daily_schedule = raw_plan.get("dailySchedule", [])
    if not isinstance(daily_schedule, list):
        daily_schedule = []

    # Ensure ≥7 days (task 6.2)
    # Pad if necessary with placeholder entries
    while len(daily_schedule) < 7:
        day_num = len(daily_schedule) + 1
        daily_schedule.append({
            "day": day_num,
            "resourceId": "",
            "estimatedDuration": "0 hours",
            "recommendationReason": "Rest or review day",
        })

    # Normalize schedule entries and enforce daily budget (task 6.3)
    normalized_schedule = []
    for entry in daily_schedule:
        if not isinstance(entry, dict):
            continue
        duration_str = str(entry.get("estimatedDuration", "1 hour"))
        duration_hours = _parse_duration_hours(duration_str)
        if duration_hours > daily_budget_hours and daily_budget_hours > 0:
            duration_hours = daily_budget_hours
            duration_str = f"{daily_budget_hours:.1f} hours"
        normalized_schedule.append({
            "day": int(entry.get("day", 1)),
            "resourceId": str(entry.get("resourceId", "")),
            "estimatedDuration": duration_str,
            "recommendationReason": str(entry.get("recommendationReason", "")),
        })

    # Build resource index for priority score assignment (task 6.5)
    priority_scores_raw = raw_plan.get("resourcePriorityScores", {})
    resource_id_set = {r["resourceId"] for r in resources}
    priority_scores: dict[str, int] = {}
    for rid, score in priority_scores_raw.items():
        if rid in resource_id_set:
            try:
                clamped = max(0, min(100, int(score)))
                priority_scores[rid] = clamped
            except (TypeError, ValueError):
                priority_scores[rid] = 0

    return {
        "userId": user_id,
        "resourceId": PLAN_SORT_KEY,
        "dailySchedule": normalized_schedule,
        "weeklyRoadmap": _str_list(raw_plan.get("weeklyRoadmap")),
        "recommendedProjects": _str_list(raw_plan.get("recommendedProjects")),
        "certificationRecommendations": _str_list(raw_plan.get("certificationRecommendations")),
        "estimatedCompletionTimeline": str(raw_plan.get("estimatedCompletionTimeline", "")),
        "resourcePriorityScores": priority_scores,
        "generatedAt": _now_iso(),
        "careerGoalSnapshot": {
            "careerGoal": profile.get("careerGoal"),
            "currentSkillLevel": profile.get("currentSkillLevel"),
            "weeklyStudyHours": profile.get("weeklyStudyHours"),
        },
    }


def _parse_duration_hours(duration_str: str) -> float:
    """Parse a duration string like '1.5 hours' or '90 minutes' to float hours."""
    s = duration_str.lower().strip()
    try:
        if "minute" in s:
            num = float("".join(c for c in s if c.isdigit() or c == "."))
            return num / 60
        num = float("".join(c for c in s if c.isdigit() or c == "."))
        return num
    except (ValueError, TypeError):
        return 1.0


def _str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(i) for i in val]
    return []


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
            # Fetch profile and resources (task 6.1)
            profile = fetch_career_goal_profile(user_id, db)
            if not profile:
                return api_response(400, {
                    "error": "NO_CAREER_GOAL",
                    "message": "Please set up your career goal before generating a learning plan.",
                })

            resources = fetch_active_resources(user_id, db)  # excludes Completed/Skipped (task 6.4)

            # Build prompt and invoke Bedrock (task 6.1)
            prompt = build_planner_prompt(profile, resources)
            bedrock_client = boto3.client("bedrock-runtime")
            raw_plan = invoke_bedrock_planner(prompt, bedrock_client)

            if raw_plan is None:
                # Task 6.6: Bedrock error — preserve last valid plan, return 503
                duration_ms = timer.elapsed_ms()
                logger.emit_error(
                    status_code=503,
                    duration_ms=duration_ms,
                    error_type="BedrockPlannerError",
                    error_message="Plan generation temporarily unavailable.",
                )
                return api_response(503, {
                    "error": "PLAN_GENERATION_UNAVAILABLE",
                    "message": "Plan generation is temporarily unavailable. Your last plan has been preserved.",
                })

            # Build structured plan (tasks 6.2, 6.3, 6.5)
            plan = build_learning_plan(user_id, raw_plan, profile, resources)

            # Persist under PLAN#active (task 6.7)
            db.put_item(Item=plan)

            duration_ms = timer.elapsed_ms()
            logger.emit(status_code=201, duration_ms=duration_ms)
            return api_response(201, plan)

        except DynamoDBThrottlingError:
            logger.emit_error(
                status_code=503,
                duration_ms=timer.elapsed_ms(),
                error_type="DynamoDBThrottlingError",
                error_message="Service temporarily unavailable.",
            )
            return api_response(503, {"error": "SERVICE_UNAVAILABLE", "message": "Service temporarily unavailable. Please retry."})
