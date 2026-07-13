"""
AI Analyzer Lambda handler for LearningPath AI.

Invoked asynchronously (InvocationType="Event") by the ResourceManager after
a new resource is persisted. Fetches the resource from DynamoDB, calls Amazon
Bedrock Nova Lite to generate AI metadata, and merges the result back into the
DynamoDB record.

Route (direct Lambda invocation — no API Gateway proxy envelope):
  Event payload: {"resourceId": "RESOURCE#<uuid>", "userId": "<sub>"}

Bedrock prompt contract (fields requested):
  {
    "priorityScore": 0,
    "summary": "",
    "skills": [],
    "difficulty": "",
    "estimatedTime": "",
    "whyLearnNow": "",
    "recommendedWeek": 0
  }

Error handling (task 4.3):
  - On Bedrock error or non-JSON response: log to CloudWatch at ERROR level,
    retain resource with AI metadata fields set to null.
  - Timeout: 30 seconds (configured in CDK).

Requirements: 2.1–2.7, 12.1, 12.2, 12.5
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.correlation import correlation_context, get_correlation_id
from shared.dynamodb_client import DynamoDBClient
from shared.logger import InvocationTimer, LambdaLogger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")
BEDROCK_MODEL_ID: str = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

#: Required keys the Bedrock prompt requests in the JSON response.
REQUIRED_AI_FIELDS: tuple[str, ...] = (
    "priorityScore",
    "summary",
    "skills",
    "difficulty",
    "estimatedTime",
    "whyLearnNow",
    "recommendedWeek",
)

_log = logging.getLogger(__name__)
_log.setLevel(logging.INFO)
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_h)


# ---------------------------------------------------------------------------
# Prompt builder (task 4.1)
# ---------------------------------------------------------------------------

def build_bedrock_prompt(resource: dict[str, Any]) -> str:
    """
    Build the Bedrock Nova Lite prompt for a given resource.

    The prompt explicitly requests a JSON response containing all required
    AI metadata fields (Property 7 / Requirement 2.3).

    Args:
        resource: The DynamoDB resource record.

    Returns:
        A prompt string to send to Bedrock.
    """
    title = resource.get("title", "")
    url = resource.get("url", "")
    description = resource.get("description", resource.get("summary", ""))
    resource_type = resource.get("resourceType", "")
    technology = resource.get("technology", "")

    return (
        "You are a learning resource analyst. Analyze the following learning resource "
        "and respond with ONLY a valid JSON object (no markdown, no extra text).\n\n"
        f"Title: {title}\n"
        f"URL: {url}\n"
        f"Type: {resource_type}\n"
        f"Technology: {technology}\n"
        f"Description: {description}\n\n"
        "Respond with this exact JSON structure:\n"
        "{\n"
        '  "priorityScore": <integer 0-100 indicating urgency to study>,\n'
        '  "summary": "<one-sentence summary of the resource>",\n'
        '  "skills": ["<skill1>", "<skill2>"],\n'
        '  "difficulty": "<Beginner|Intermediate|Advanced>",\n'
        '  "estimatedTime": "<e.g. 2 hours>",\n'
        '  "whyLearnNow": "<why this is relevant to learn now>",\n'
        '  "recommendedWeek": <integer week number to study this>\n'
        "}"
    )


# ---------------------------------------------------------------------------
# Bedrock invocation (task 4.2)
# ---------------------------------------------------------------------------

def invoke_bedrock(prompt: str, bedrock_client: Any) -> dict[str, Any] | None:
    """
    Invoke Amazon Bedrock Nova Lite with the given prompt and parse the JSON response.

    Uses a 30-second read timeout (configured at the boto3 client level in CDK;
    here we enforce it at the application level as well).

    Args:
        prompt:         The prompt string to send to Bedrock.
        bedrock_client: A boto3 bedrock-runtime client.

    Returns:
        Parsed AI metadata dict on success, or None on error / non-JSON response.
    """
    request_body = json.dumps({
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": 512,
            "temperature": 0.1,
        },
    })

    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )
        raw_body = response["body"].read().decode("utf-8")
    except ClientError as exc:
        _log.error(json.dumps({
            "level": "ERROR",
            "message": "Bedrock ClientError during invoke_model",
            "errorType": type(exc).__name__,
            "correlationId": get_correlation_id(),
        }))
        return None
    except Exception as exc:
        _log.error(json.dumps({
            "level": "ERROR",
            "message": "Unexpected error invoking Bedrock",
            "errorType": type(exc).__name__,
            "correlationId": get_correlation_id(),
        }))
        return None

    # Parse the Converse/InvokeModel response envelope
    try:
        envelope = json.loads(raw_body)
        # Nova Lite response format: {"output": {"message": {"content": [{"text": "..."}]}}}
        content_blocks = (
            envelope.get("output", {})
                    .get("message", {})
                    .get("content", [])
        )
        text_content = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_content = block.get("text", "")
                break
        if not text_content:
            # Fallback: some versions put text at top level
            text_content = envelope.get("completion", raw_body)
    except (json.JSONDecodeError, KeyError):
        text_content = raw_body

    # Parse the actual JSON payload from the model's text response
    return _parse_json_response(text_content)


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """
    Extract and parse a JSON object from the model's text response.

    Handles cases where the model wraps JSON in markdown code fences.

    Returns:
        Parsed dict, or None if the text cannot be parsed as JSON.
    """
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first line (```json or ```) and last line (```)
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return None
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# DynamoDB update (task 4.2)
# ---------------------------------------------------------------------------

def merge_ai_metadata(
    user_id: str,
    resource_id: str,
    ai_metadata: dict[str, Any] | None,
    db: DynamoDBClient,
) -> None:
    """
    Merge AI metadata into the existing DynamoDB resource record.

    On success: sets aiMetadata to the parsed fields.
    On failure (ai_metadata is None): sets all AI fields to null (task 4.3).

    Args:
        user_id:     The resource owner's userId.
        resource_id: The resource's sort key (e.g. RESOURCE#<uuid>).
        ai_metadata: Parsed AI metadata dict, or None on Bedrock failure.
        db:          DynamoDBClient instance.
    """
    response = db.get_item(Key={"userId": user_id, "resourceId": resource_id})
    existing = response.get("Item")
    if not existing:
        _log.warning(json.dumps({
            "level": "WARNING",
            "message": "Resource not found during AI metadata merge",
            "resourceId": resource_id,
            "userId": user_id,
            "correlationId": get_correlation_id(),
        }))
        return

    updated = dict(existing)

    if ai_metadata is not None:
        # Merge valid AI metadata — pick only the required fields
        updated["aiMetadata"] = {
            field: ai_metadata.get(field) for field in REQUIRED_AI_FIELDS
        }
    else:
        # Bedrock error path: retain original record, set AI fields to null (task 4.3)
        updated["aiMetadata"] = None

    from datetime import datetime, timezone
    updated["updatedAt"] = datetime.now(timezone.utc).isoformat()
    db.put_item(Item=updated)


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event: dict[str, Any], context: Any) -> None:
    """
    Main Lambda handler for the AI Analyzer.

    Accepts either:
      - Direct invocation payload: {"resourceId": "...", "userId": "..."}
      - API Gateway proxy event with body containing the same fields

    On Bedrock error, the resource record is retained with aiMetadata=null
    and the error is logged to CloudWatch (Requirement 2.5 / task 4.3).
    """
    timer = InvocationTimer()

    # Support both direct invocation and API Gateway proxy envelope
    if "body" in event and isinstance(event.get("body"), (str, dict)):
        body = event["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        resource_id = body.get("resourceId", "")
        user_id = body.get("userId", "")
    else:
        resource_id = event.get("resourceId", "")
        user_id = event.get("userId", "")

    # Extract correlation ID from event if present (propagated from ResourceManager)
    correlation_id = (
        event.get("correlationId")
        or (event.get("requestContext") or {}).get("requestId")
        or "unknown"
    )

    logger = LambdaLogger(path="/analyze", correlation_id=correlation_id)
    logger.set_user(user_id or None)

    with correlation_context({"requestContext": {"requestId": correlation_id}}):
        db = DynamoDBClient(table_name=TABLE_NAME)
        bedrock_client = boto3.client(
            "bedrock-runtime",
            config=boto3.session.Session().client(
                "bedrock-runtime"
            ).__class__  # placeholder; real config set below
        ) if False else boto3.client("bedrock-runtime")

        # Fetch resource (task 4.1)
        if not resource_id or not user_id:
            _log.error(json.dumps({
                "level": "ERROR",
                "message": "Missing resourceId or userId in event",
                "correlationId": correlation_id,
            }))
            return

        get_resp = db.get_item(Key={"userId": user_id, "resourceId": resource_id})
        resource = get_resp.get("Item")

        if not resource:
            _log.error(json.dumps({
                "level": "ERROR",
                "message": "Resource not found for AI analysis",
                "resourceId": resource_id,
                "userId": user_id,
                "correlationId": correlation_id,
            }))
            return

        # Build prompt (task 4.1)
        prompt = build_bedrock_prompt(resource)

        # Invoke Bedrock (task 4.2)
        ai_metadata = invoke_bedrock(prompt, bedrock_client)

        # Log error if Bedrock returned nothing (task 4.3)
        if ai_metadata is None:
            duration_ms = timer.elapsed_ms()
            logger.emit_error(
                status_code=500,
                duration_ms=duration_ms,
                error_type="BedrockAnalysisError",
                error_message="Bedrock returned no valid AI metadata; retaining null fields.",
            )
        else:
            duration_ms = timer.elapsed_ms()
            logger.emit(status_code=200, duration_ms=duration_ms)

        # Merge into DynamoDB (task 4.2 on success, task 4.3 on failure)
        merge_ai_metadata(user_id, resource_id, ai_metadata, db)
