"""
Quiz Generator Lambda for LearningPath AI.

Routes:
  POST /quiz — Generate quiz questions based on user's resources and career goal
  GET  /quiz — Get the last generated quiz

Uses Amazon Bedrock (Nova Lite) to generate exam-style multiple-choice questions
tailored to the user's career goal and resources.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.auth import get_user_id as _get_user_id
from shared.correlation import correlation_context
from shared.dynamodb_client import DynamoDBClient, DynamoDBThrottlingError
from shared.error_handler import api_response, lambda_error_handler
from shared.logger import InvocationTimer, make_logger

TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "LearningPathAI")
BEDROCK_MODEL_ID: str = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

QUIZ_SORT_KEY = "QUIZ#latest"
PROFILE_SORT_KEY = "PROFILE#career_goal"


def _fetch_resources(user_id: str, db: DynamoDBClient) -> list[dict]:
    from boto3.dynamodb.conditions import Key
    resp = db.query(
        KeyConditionExpression=Key("userId").eq(user_id) & Key("resourceId").begins_with("RESOURCE#")
    )
    return resp.get("Items", [])


def _fetch_profile(user_id: str, db: DynamoDBClient) -> dict | None:
    resp = db.get_item(Key={"userId": user_id, "resourceId": PROFILE_SORT_KEY})
    return resp.get("Item")


def _fetch_last_quiz(user_id: str, db: DynamoDBClient) -> dict | None:
    resp = db.get_item(Key={"userId": user_id, "resourceId": QUIZ_SORT_KEY})
    return resp.get("Item")


def _build_quiz_prompt(profile: dict, resources: list[dict], num_questions: int = 5) -> str:
    career_goal = profile.get("careerGoal", "Cloud Engineer")
    skill_level = profile.get("currentSkillLevel", "Intermediate")

    resource_context = []
    for r in resources:
        title = r.get("title", "")
        tech = r.get("technology", "")
        tags = ", ".join(r.get("tags", []))
        summary = (r.get("aiMetadata") or {}).get("summary", "")
        resource_context.append(f"- {title} (Technology: {tech}, Tags: {tags})")
        if summary:
            resource_context.append(f"  Summary: {summary}")

    resources_text = "\n".join(resource_context) if resource_context else "AWS Solutions Architect Professional topics"

    return (
        f"You are an expert exam question writer for {career_goal} certification.\n\n"
        f"Learner's current level: {skill_level}\n"
        f"Their study resources:\n{resources_text}\n\n"
        f"Generate {num_questions} multiple-choice questions that test knowledge relevant to "
        f"the {career_goal} certification. Each question should:\n"
        f"- Be exam-style (scenario-based where possible)\n"
        f"- Have 4 options (A, B, C, D)\n"
        f"- Have exactly one correct answer\n"
        f"- Include a brief explanation of why the correct answer is right\n"
        f"- Range from {skill_level} to advanced difficulty\n\n"
        f"Respond with ONLY a valid JSON object (no markdown, no extra text):\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "id": 1,\n'
        '      "question": "<scenario or question text>",\n'
        '      "options": {"A": "<option>", "B": "<option>", "C": "<option>", "D": "<option>"},\n'
        '      "correctAnswer": "<A|B|C|D>",\n'
        '      "explanation": "<why this is correct>",\n'
        '      "topic": "<e.g. VPC, IAM, S3>",\n'
        '      "difficulty": "<Easy|Medium|Hard>"\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def _invoke_bedrock_quiz(prompt: str, bedrock_client: Any) -> dict | None:
    """Invoke Bedrock to generate quiz questions."""
    try:
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0.4},
        )
        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])
        text = ""
        for block in content_blocks:
            if isinstance(block, dict) and "text" in block:
                text = block["text"]
                break
        if not text:
            return None
    except (ClientError, Exception):
        return None

    # Parse JSON from response
    try:
        # Try to extract JSON from possible markdown wrapping
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            lines = lines[1:]  # remove opening ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean = "\n".join(lines)
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return None


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
        http_method = (event.get("httpMethod") or "POST").upper()

        # GET /quiz — return last quiz
        if http_method == "GET":
            try:
                quiz = _fetch_last_quiz(user_id, db)
                if not quiz:
                    return api_response(404, {"error": "NOT_FOUND", "message": "No quiz generated yet."})
                logger.emit(status_code=200, duration_ms=timer.elapsed_ms())
                return api_response(200, quiz)
            except DynamoDBThrottlingError:
                return api_response(503, {"error": "SERVICE_UNAVAILABLE", "message": "Service temporarily unavailable."})

        # POST /quiz — generate new quiz
        try:
            profile = _fetch_profile(user_id, db)
            resources = _fetch_resources(user_id, db)

            # Parse optional num_questions from body
            body = json.loads(event.get("body") or "{}")
            num_questions = min(int(body.get("numQuestions", 5)), 10)

            prompt = _build_quiz_prompt(profile or {"careerGoal": "AWS Solutions Architect Professional"}, resources, num_questions)
            bedrock_client = boto3.client("bedrock-runtime")
            result = _invoke_bedrock_quiz(prompt, bedrock_client)

            if result is None:
                logger.emit_error(status_code=503, duration_ms=timer.elapsed_ms(),
                                  error_type="BedrockQuizError",
                                  error_message="Quiz generation failed.")
                return api_response(503, {"error": "QUIZ_GENERATION_FAILED", "message": "Quiz generation temporarily unavailable. Please try again."})

            # Save quiz to DynamoDB
            from datetime import datetime, timezone
            quiz_item = {
                "userId": user_id,
                "resourceId": QUIZ_SORT_KEY,
                "questions": result.get("questions", []),
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "careerGoal": (profile or {}).get("careerGoal", "General"),
                "numQuestions": len(result.get("questions", [])),
            }
            db.put_item(Item=quiz_item)

            logger.emit(status_code=201, duration_ms=timer.elapsed_ms())
            return api_response(201, quiz_item)

        except DynamoDBThrottlingError:
            return api_response(503, {"error": "SERVICE_UNAVAILABLE", "message": "Service temporarily unavailable."})
