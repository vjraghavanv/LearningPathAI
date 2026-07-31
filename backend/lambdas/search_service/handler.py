"""
SearchService Lambda handler for LearningPath AI.

Route:
  GET /search — filter user's resources by one or more parameters

Tasks covered:
  9.1  Parse and validate filter parameters; return HTTP 400 for unrecognized keys
  9.2  AND-logic filter evaluation across all supplied filters
  9.3  Return empty list with HTTP 200 when no resources match

Supported filter keys:
  technology, difficulty, resourceType, certificationTag, skillTag, tag

Requirements: 8.1–8.6, 9.1–9.6, 12.1, 12.2
"""

from __future__ import annotations

import os
from typing import Any

from shared.correlation import correlation_context
from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import InvocationTimer, make_logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")

# All supported filter keys (Requirement 8.2)
SUPPORTED_FILTER_KEYS: frozenset[str] = frozenset(
    {"technology", "difficulty", "resourceType", "certificationTag", "skillTag", "tag"}
)


# ---------------------------------------------------------------------------
# Helper: extract userId from JWT authorizer context
# ---------------------------------------------------------------------------

from shared.auth import get_user_id as _get_user_id


# ---------------------------------------------------------------------------
# Helper: extract query string parameters safely
# ---------------------------------------------------------------------------

def _get_query_params(event: dict) -> dict[str, str]:
    params = event.get("queryStringParameters") or {}
    return {k: v for k, v in params.items() if v is not None}


# ---------------------------------------------------------------------------
# Filter logic (task 9.2) — AND-logic across all supplied filters
# ---------------------------------------------------------------------------

def _resource_matches(resource: dict, filters: dict[str, str]) -> bool:
    """
    Return True if the resource satisfies ALL supplied filters (AND logic).

    Filter semantics:
    - technology     : exact match on resource["technology"] (case-insensitive)
    - difficulty     : exact match on resource["difficulty"] (case-insensitive)
    - resourceType   : exact match on resource["resourceType"] (case-insensitive)
    - certificationTag: substring match within resource["tags"] list (case-insensitive)
    - skillTag       : substring match within aiMetadata["skills"] list (case-insensitive)
    - tag            : substring match within resource["tags"] list (case-insensitive)
    """
    for key, value in filters.items():
        v_lower = value.lower()

        if key == "technology":
            if (resource.get("technology") or "").lower() != v_lower:
                return False

        elif key == "difficulty":
            if (resource.get("difficulty") or "").lower() != v_lower:
                return False

        elif key == "resourceType":
            if (resource.get("resourceType") or "").lower() != v_lower:
                return False

        elif key == "tag":
            tags = [t.lower() for t in (resource.get("tags") or [])]
            if v_lower not in tags:
                return False

        elif key == "certificationTag":
            # Certification tags stored in resource["tags"] list
            tags = [t.lower() for t in (resource.get("tags") or [])]
            if not any(v_lower in t for t in tags):
                return False

        elif key == "skillTag":
            # Skill tags stored in aiMetadata["skills"] list
            ai = resource.get("aiMetadata") or {}
            skills = [s.lower() for s in (ai.get("skills") or [])]
            if not any(v_lower in s for s in skills):
                return False

    return True


# ---------------------------------------------------------------------------
# Core search handler (tasks 9.1, 9.2, 9.3)
# ---------------------------------------------------------------------------

def handle_search(
    user_id: str,
    query_params: dict[str, str],
    db: DynamoDBClient,
) -> dict:
    """
    Tasks 9.1–9.3:
    - Validate filter keys (400 on unrecognized)
    - Fetch all resources for userId
    - Apply AND-logic filtering
    - Return matching list (empty list is valid, HTTP 200)
    """
    # Validate filter keys (task 9.1, Requirement 8.6)
    unrecognized = set(query_params.keys()) - SUPPORTED_FILTER_KEYS
    if unrecognized:
        return api_response(400, {
            "error": "VALIDATION_ERROR",
            "message": (
                f"Unrecognized filter key(s): {', '.join(sorted(unrecognized))}. "
                f"Supported keys: {', '.join(sorted(SUPPORTED_FILTER_KEYS))}."
            ),
        })

    # Fetch all resources for this userId (Requirement 8.1)
    from boto3.dynamodb.conditions import Key
    resp = db.query(
        KeyConditionExpression=Key("userId").eq(user_id)
        & Key("resourceId").begins_with("RESOURCE#")
    )
    all_resources = resp.get("Items", [])

    # Apply AND-logic filter (task 9.2) — empty filters returns everything
    if query_params:
        matched = [r for r in all_resources if _resource_matches(r, query_params)]
    else:
        matched = all_resources

    # Task 9.3: empty list is a valid 200 response (Requirement 8.4)
    return api_response(200, matched)


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
            return api_response(401, {
                "error": "UNAUTHORIZED",
                "message": "Missing or invalid authorization.",
            })

        logger.set_user(user_id)
        http_method = (event.get("httpMethod") or "").upper()

        db = DynamoDBClient(table_name=TABLE_NAME)

        try:
            if http_method == "GET":
                query_params = _get_query_params(event)
                result = handle_search(user_id, query_params, db)
            else:
                result = api_response(405, {
                    "error": "METHOD_NOT_ALLOWED",
                    "message": f"Method {http_method} not supported.",
                })
        except DynamoDBThrottlingError:
            logger.emit_error(
                status_code=503,
                duration_ms=timer.elapsed_ms(),
                error_type="DynamoDBThrottlingError",
                error_message="Service temporarily unavailable.",
            )
            return api_response(503, {
                "error": "SERVICE_UNAVAILABLE",
                "message": "Service temporarily unavailable. Please retry.",
            })

        status_code = result.get("statusCode", 200)
        if status_code >= 400:
            logger.emit_error(status_code=status_code, duration_ms=timer.elapsed_ms())
        else:
            logger.emit(status_code=status_code, duration_ms=timer.elapsed_ms())

        return result
