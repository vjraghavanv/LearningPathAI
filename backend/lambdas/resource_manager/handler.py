"""
ResourceManager Lambda handler for LearningPath AI.

Routes HTTP requests from API Gateway to the appropriate CRUD operation for
learning resources stored in DynamoDB.

Routes:
  POST   /resources          — create a new resource (task 3.1)
  GET    /resources          — list all resources for the caller (task 3.2)
  PUT    /resources/{id}     — update a resource (task 3.3)
  DELETE /resources/{id}     — delete a resource (task 3.4)

Input validation (task 3.5):
  - Required fields for POST: title, url, resourceType
  - resourceType must be one of the six accepted values
  - difficulty (optional) must be one of: Beginner, Intermediate, Advanced
  - All validation errors return HTTP 400 with a structured JSON body

Ownership enforcement:
  - PUT and DELETE check that the resource's stored userId matches the caller.
  - Mismatches return HTTP 403.

AI_Analyzer trigger:
  - After persisting a new resource, the AI_Analyzer Lambda is invoked
    asynchronously (InvocationType="Event") with the new resourceId and userId.

Environment variables:
  DYNAMODB_TABLE_NAME       — DynamoDB table name (default: LearningPathAI)
  AI_ANALYZER_FUNCTION_NAME — Name/ARN of the AI_Analyzer Lambda function

Requirement references: 1.1–1.8, 9.5, 12.1, 12.2, 12.5
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.correlation import correlation_context
from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import InvocationTimer, make_logger

# ---------------------------------------------------------------------------
# Constants — validation
# ---------------------------------------------------------------------------

VALID_RESOURCE_TYPES: frozenset[str] = frozenset(
    {
        "Technical Article",
        "Documentation",
        "YouTube Video",
        "Online Course",
        "PDF",
        "GitHub Repository",
    }
)

VALID_DIFFICULTY_VALUES: frozenset[str] = frozenset(
    {"Beginner", "Intermediate", "Advanced"}
)

VALID_LEARNING_STATUS_VALUES: frozenset[str] = frozenset(
    {"Not Started", "In Progress", "Completed", "Skipped"}
)

UPDATABLE_METADATA_FIELDS: tuple[str, ...] = (
    "title",
    "url",
    "resourceType",
    "estimatedDuration",
    "difficulty",
    "tags",
    "technology",
    "learningStatus",
    "completionTimestamp",
    "completionPercentage",
)

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")
AI_ANALYZER_FUNCTION_NAME: str | None = os.environ.get("AI_ANALYZER_FUNCTION_NAME")


# ---------------------------------------------------------------------------
# Helper: extract userId from JWT authorizer context
# ---------------------------------------------------------------------------

from shared.auth import get_user_id as _get_user_id


# ---------------------------------------------------------------------------
# Helper: UTC ISO-8601 timestamp
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Helper: parse JSON body safely
# ---------------------------------------------------------------------------

def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """
    Parse the request body from the API Gateway event.

    Returns an empty dict if the body is absent or unparseable.
    """
    body = event.get("body") or "{}"
    if isinstance(body, str):
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return {}
    if isinstance(body, dict):
        return body
    return {}


# ---------------------------------------------------------------------------
# Helper: extract resource id from path parameters
# ---------------------------------------------------------------------------

def _get_resource_id(event: dict[str, Any]) -> str | None:
    """
    Extract the ``{id}`` path parameter from the API Gateway event.

    The path parameter can be stored under the key ``id`` (REST API) or
    ``resourceId`` depending on the API Gateway configuration. Both are
    attempted.
    """
    params = event.get("pathParameters") or {}
    return params.get("id") or params.get("resourceId")


# ---------------------------------------------------------------------------
# Input validation (task 3.5)
# ---------------------------------------------------------------------------

def _validate_resource_type(value: Any) -> tuple[bool, str]:
    """
    Validate the resourceType field.

    Returns:
        (True, "") on success; (False, error_message) on failure.
    """
    if value not in VALID_RESOURCE_TYPES:
        return False, (
            f"Invalid resourceType '{value}'. "
            f"Must be one of: {', '.join(sorted(VALID_RESOURCE_TYPES))}."
        )
    return True, ""


def _validate_difficulty(value: Any) -> tuple[bool, str]:
    """
    Validate the optional difficulty field.

    Returns:
        (True, "") on success; (False, error_message) on failure.
    """
    if value not in VALID_DIFFICULTY_VALUES:
        return False, (
            f"Invalid difficulty '{value}'. "
            f"Must be one of: {', '.join(sorted(VALID_DIFFICULTY_VALUES))}."
        )
    return True, ""


def _validation_error(message: str, field: str | None = None) -> dict[str, Any]:
    """Build a 400 response body for a validation failure."""
    body: dict[str, Any] = {"error": "VALIDATION_ERROR", "message": message}
    if field:
        body["field"] = field
    return api_response(400, body)


def _forbidden_error() -> dict[str, Any]:
    """Build a 403 response for ownership check failures."""
    return api_response(
        403,
        {
            "error": "FORBIDDEN",
            "message": "You do not have permission to access this resource.",
        },
    )


# ---------------------------------------------------------------------------
# POST /resources — create resource (task 3.1)
# ---------------------------------------------------------------------------

def _handle_post(
    user_id: str,
    body: dict[str, Any],
    db: DynamoDBClient,
    lambda_client: Any,
) -> dict[str, Any]:
    """
    Persist a new resource to DynamoDB and trigger the AI_Analyzer asynchronously.

    Required fields: title, url, resourceType
    """
    # --- Required field validation (task 3.5) ---
    for field in ("title", "url", "resourceType"):
        if not body.get(field):
            return _validation_error(
                f"Required field '{field}' is missing or empty.", field=field
            )

    # --- resourceType enum validation (task 3.5) ---
    ok, msg = _validate_resource_type(body["resourceType"])
    if not ok:
        return _validation_error(msg, field="resourceType")

    # --- optional difficulty validation (task 3.5) ---
    if "difficulty" in body and body["difficulty"]:
        ok, msg = _validate_difficulty(body["difficulty"])
        if not ok:
            return _validation_error(msg, field="difficulty")

    # --- Build the resource item ---
    resource_uuid = str(uuid.uuid4())
    resource_id = f"RESOURCE#{resource_uuid}"
    now = _now_iso()

    item: dict[str, Any] = {
        "userId": user_id,
        "resourceId": resource_id,
        "title": body["title"],
        "url": body["url"],
        "resourceType": body["resourceType"],
        "estimatedDuration": body.get("estimatedDuration", ""),
        "difficulty": body.get("difficulty", ""),
        "tags": body.get("tags", []),
        "technology": body.get("technology", ""),
        "learningStatus": body.get("learningStatus", "Not Started"),
        "completionTimestamp": None,
        "completionPercentage": 0,
        "aiMetadata": None,
        "createdAt": now,
        "updatedAt": now,
    }

    # --- Persist to DynamoDB ---
    db.put_item(Item=item)

    # --- Trigger AI_Analyzer asynchronously ---
    if AI_ANALYZER_FUNCTION_NAME and lambda_client is not None:
        try:
            lambda_client.invoke(
                FunctionName=AI_ANALYZER_FUNCTION_NAME,
                InvocationType="Event",
                Payload=json.dumps({"resourceId": resource_id, "userId": user_id}).encode(),
            )
        except Exception:
            # Non-fatal: AI analysis is best-effort; the resource is already saved.
            pass

    return api_response(201, item)


# ---------------------------------------------------------------------------
# GET /resources — list resources (task 3.2)
# ---------------------------------------------------------------------------

def _handle_get(user_id: str, db: DynamoDBClient) -> dict[str, Any]:
    """
    Return all resources for the authenticated userId from DynamoDB.

    Uses a DynamoDB Query on the partition key and filters to items whose
    sort key starts with ``RESOURCE#``.
    """
    from boto3.dynamodb.conditions import Key

    response = db.query(
        KeyConditionExpression=Key("userId").eq(user_id)
        & Key("resourceId").begins_with("RESOURCE#")
    )
    items = response.get("Items", [])
    return api_response(200, items)


# ---------------------------------------------------------------------------
# PUT /resources/{id} — update resource (task 3.3)
# ---------------------------------------------------------------------------

def _handle_put(
    user_id: str,
    resource_id: str,
    body: dict[str, Any],
    db: DynamoDBClient,
) -> dict[str, Any]:
    """
    Update metadata fields of an existing resource after verifying ownership.

    Returns the full updated item.
    """
    # --- Fetch existing item ---
    lookup_id = resource_id
    response = db.get_item(Key={"userId": user_id, "resourceId": lookup_id})
    existing = response.get("Item")

    if not existing and not resource_id.startswith("RESOURCE#"):
        lookup_id = f"RESOURCE#{resource_id}"
        response = db.get_item(Key={"userId": user_id, "resourceId": lookup_id})
        existing = response.get("Item")

    if not existing:
        return api_response(404, {"error": "NOT_FOUND", "message": "Resource not found."})

    # --- Ownership check ---
    if existing.get("userId") != user_id:
        return _forbidden_error()

    # --- resourceType enum validation if being updated ---
    if "resourceType" in body and body["resourceType"]:
        ok, msg = _validate_resource_type(body["resourceType"])
        if not ok:
            return _validation_error(msg, field="resourceType")

    # --- difficulty enum validation if being updated ---
    if "difficulty" in body and body["difficulty"]:
        ok, msg = _validate_difficulty(body["difficulty"])
        if not ok:
            return _validation_error(msg, field="difficulty")

    # --- Overwrite metadata fields ---
    updated = dict(existing)
    for field in UPDATABLE_METADATA_FIELDS:
        if field in body:
            updated[field] = body[field]
    updated["updatedAt"] = _now_iso()

    db.put_item(Item=updated)
    return api_response(200, updated)


# ---------------------------------------------------------------------------
# DELETE /resources/{id} — delete resource (task 3.4)
# ---------------------------------------------------------------------------

def _handle_delete(user_id: str, resource_id: str, db: DynamoDBClient) -> dict[str, Any]:
    """
    Delete an existing resource after verifying ownership.

    Returns 204 No Content on success.
    """
    # Normalize: try as-is first, then with RESOURCE# prefix
    lookup_id = resource_id
    response = db.get_item(Key={"userId": user_id, "resourceId": lookup_id})
    existing = response.get("Item")

    if not existing and not resource_id.startswith("RESOURCE#"):
        lookup_id = f"RESOURCE#{resource_id}"
        response = db.get_item(Key={"userId": user_id, "resourceId": lookup_id})
        existing = response.get("Item")

    if not existing:
        return api_response(404, {"error": "NOT_FOUND", "message": "Resource not found."})

    # --- Ownership check ---
    if existing.get("userId") != user_id:
        return _forbidden_error()

    db.delete_item(Key={"userId": user_id, "resourceId": lookup_id})
    return api_response(204, "")


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Main Lambda handler — routes by HTTP method and path.

    Expected to be invoked via API Gateway Lambda proxy integration.
    The JWT authorizer must inject ``event["requestContext"]["authorizer"]["claims"]["sub"]``
    with the authenticated user's sub claim.
    """
    timer = InvocationTimer()
    logger = make_logger(event, context)

    with correlation_context(event):
        # --- Extract userId from JWT authorizer context ---
        user_id = _get_user_id(event)
        if not user_id:
            return api_response(
                401,
                {"error": "UNAUTHORIZED", "message": "Missing or invalid authorization."},
            )

        logger.set_user(user_id)

        # --- Route the request ---
        http_method: str = (event.get("httpMethod") or "").upper()
        path: str = event.get("path") or event.get("rawPath") or ""

        db = DynamoDBClient(table_name=TABLE_NAME)
        lambda_client = boto3.client("lambda") if AI_ANALYZER_FUNCTION_NAME else None

        try:
            if http_method == "POST" and path.rstrip("/").endswith("/resources"):
                body = _parse_body(event)
                result = _handle_post(user_id, body, db, lambda_client)

            elif http_method == "GET" and path.rstrip("/").endswith("/resources"):
                result = _handle_get(user_id, db)

            elif http_method == "PUT":
                resource_id = _get_resource_id(event)
                if not resource_id:
                    result = _validation_error("Resource ID is required.", field="id")
                else:
                    body = _parse_body(event)
                    result = _handle_put(user_id, resource_id, body, db)

            elif http_method == "DELETE":
                resource_id = _get_resource_id(event)
                if not resource_id:
                    result = _validation_error("Resource ID is required.", field="id")
                else:
                    result = _handle_delete(user_id, resource_id, db)

            else:
                result = api_response(
                    405,
                    {"error": "METHOD_NOT_ALLOWED", "message": f"Method {http_method} not supported."},
                )

        except DynamoDBThrottlingError:
            duration_ms = timer.elapsed_ms()
            logger.emit_error(status_code=503, duration_ms=duration_ms, error_type="DynamoDBThrottlingError", error_message="Service temporarily unavailable due to high load.")
            return api_response(
                503,
                {"error": "SERVICE_UNAVAILABLE", "message": "Service temporarily unavailable. Please retry."},
            )

        duration_ms = timer.elapsed_ms()
        status_code: int = result.get("statusCode", 200)
        if status_code >= 400:
            logger.emit_error(status_code=status_code, duration_ms=duration_ms)
        else:
            logger.emit(status_code=status_code, duration_ms=duration_ms)

        return result
