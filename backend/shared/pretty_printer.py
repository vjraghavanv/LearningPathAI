"""
Pretty Printer utility for LearningPath AI.

Serializes DynamoDB resource records and Learning_Plan objects back into the
exact JSON structure expected by Bedrock prompts. This supports the round-trip
correctness guarantee: re-analyzing or re-planning with the same data must
produce an equivalent result.

Requirement 2.7 (Property 9):
    The Pretty_Printer SHALL format AI metadata stored in DynamoDB back into
    the same JSON structure accepted by the Bedrock prompt, so that re-analysis
    of a Resource produces an equivalent result (round-trip property).

Requirement 4.10 (Property 15):
    The Pretty_Printer SHALL format a Learning_Plan object back into the JSON
    structure accepted by the Bedrock prompt, so that re-planning with the same
    inputs produces an equivalent plan (round-trip property).
"""

from __future__ import annotations

from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# AI Metadata serialization (Property 9 / Requirement 2.7)
# ---------------------------------------------------------------------------

#: The exact set of keys requested in the AI_Analyzer Bedrock prompt.
AI_METADATA_KEYS: tuple[str, ...] = (
    "priorityScore",
    "summary",
    "skills",
    "difficulty",
    "estimatedTime",
    "whyLearnNow",
    "recommendedWeek",
)

#: Defaults applied when a field is absent or None in the stored record.
_AI_METADATA_DEFAULTS: dict[str, Any] = {
    "priorityScore": 0,
    "summary": "",
    "skills": [],
    "difficulty": "",
    "estimatedTime": "",
    "whyLearnNow": "",
    "recommendedWeek": 0,
}


def serialize_ai_metadata(ai_metadata: Optional[dict]) -> dict:
    """
    Serialize a resource's ``aiMetadata`` DynamoDB record into the JSON
    structure accepted by the AI_Analyzer Bedrock prompt.

    The output contains exactly the keys defined in the Bedrock prompt
    contract, in the same order, using appropriate defaults for any
    missing or None values:

    .. code-block:: json

        {
            "priorityScore": 0,
            "summary": "",
            "skills": [],
            "difficulty": "",
            "estimatedTime": "",
            "whyLearnNow": "",
            "recommendedWeek": 0
        }

    This guarantees that the serialized output can be embedded directly
    in a Bedrock prompt without further processing, satisfying the
    round-trip correctness property (Property 9).

    Args:
        ai_metadata: The ``aiMetadata`` sub-document from a DynamoDB resource
                     record.  May be ``None`` or an incomplete dict; missing
                     fields are filled with their defaults.

    Returns:
        A dict with exactly the seven AI metadata keys expected by the
        Bedrock prompt, with all fields present and typed correctly.

    Examples::

        # Full record
        result = serialize_ai_metadata({
            "priorityScore": 85,
            "summary": "Intro to EC2",
            "skills": ["AWS", "EC2"],
            "difficulty": "Intermediate",
            "estimatedTime": "2 hours",
            "whyLearnNow": "Core compute service",
            "recommendedWeek": 2,
        })
        # result == {
        #     "priorityScore": 85, "summary": "Intro to EC2",
        #     "skills": ["AWS", "EC2"], "difficulty": "Intermediate",
        #     "estimatedTime": "2 hours", "whyLearnNow": "Core compute service",
        #     "recommendedWeek": 2
        # }

        # None input — returns all defaults
        result = serialize_ai_metadata(None)
        # result == {"priorityScore": 0, "summary": "", "skills": [], ...}
    """
    source: dict = ai_metadata if isinstance(ai_metadata, dict) else {}

    return {
        key: _coerce_ai_field(key, source.get(key, _AI_METADATA_DEFAULTS[key]))
        for key in AI_METADATA_KEYS
    }


# ---------------------------------------------------------------------------
# Learning Plan serialization (Property 15 / Requirement 4.10)
# ---------------------------------------------------------------------------

#: Keys included per daily schedule entry in the Bedrock prompt contract.
DAILY_SCHEDULE_KEYS: tuple[str, ...] = (
    "day",
    "resourceId",
    "estimatedDuration",
    "recommendationReason",
)

#: Defaults for daily schedule entry fields.
_DAILY_SCHEDULE_DEFAULTS: dict[str, Any] = {
    "day": 1,
    "resourceId": "",
    "estimatedDuration": "",
    "recommendationReason": "",
}

#: Top-level Learning_Plan keys in the Bedrock prompt contract.
LEARNING_PLAN_KEYS: tuple[str, ...] = (
    "dailySchedule",
    "weeklyRoadmap",
    "recommendedProjects",
    "certificationRecommendations",
    "estimatedCompletionTimeline",
)

#: Defaults applied when a top-level Learning_Plan field is absent or None.
_LEARNING_PLAN_DEFAULTS: dict[str, Any] = {
    "dailySchedule": [],
    "weeklyRoadmap": [],
    "recommendedProjects": [],
    "certificationRecommendations": [],
    "estimatedCompletionTimeline": "",
}


def serialize_learning_plan(learning_plan: Optional[dict]) -> dict:
    """
    Serialize a Learning_Plan DynamoDB record into the JSON structure accepted
    by the AI_Planner Bedrock prompt.

    The output contains exactly the top-level keys defined in the Bedrock
    prompt contract. The ``dailySchedule`` entries are projected to only the
    four fields the prompt expects (``day``, ``resourceId``,
    ``estimatedDuration``, ``recommendationReason``); the ``date`` field
    stored in DynamoDB is intentionally excluded.

    .. code-block:: json

        {
            "dailySchedule": [
                {
                    "day": 1,
                    "resourceId": "",
                    "estimatedDuration": "",
                    "recommendationReason": ""
                }
            ],
            "weeklyRoadmap": [],
            "recommendedProjects": [],
            "certificationRecommendations": [],
            "estimatedCompletionTimeline": ""
        }

    This guarantees that the serialized output can be embedded directly in a
    Bedrock prompt without further processing, satisfying the round-trip
    correctness property (Property 15).

    Args:
        learning_plan: The Learning_Plan DynamoDB record (keyed by
                       ``PLAN#active``). May be ``None`` or an incomplete
                       dict; missing fields are filled with their defaults.

    Returns:
        A dict with exactly the five top-level keys expected by the Bedrock
        prompt, with all fields present and typed correctly.

    Examples::

        record = {
            "userId": "user-1",
            "resourceId": "PLAN#active",
            "dailySchedule": [
                {
                    "day": 1,
                    "date": "2024-01-15",
                    "resourceId": "RESOURCE#abc",
                    "estimatedDuration": "1 hour",
                    "recommendationReason": "Start with basics",
                }
            ],
            "weeklyRoadmap": ["Week 1: Foundations"],
            "recommendedProjects": ["Build a CLI tool"],
            "certificationRecommendations": ["AWS SAA"],
            "estimatedCompletionTimeline": "3 months",
        }
        result = serialize_learning_plan(record)
        # result["dailySchedule"][0] does NOT contain "date"
        # result["dailySchedule"][0]["resourceId"] == "RESOURCE#abc"
    """
    source: dict = learning_plan if isinstance(learning_plan, dict) else {}

    # Serialize dailySchedule entries, stripping DynamoDB-only fields
    raw_schedule = source.get("dailySchedule", None)
    if isinstance(raw_schedule, list):
        daily_schedule: List[dict] = [
            _serialize_schedule_entry(entry) for entry in raw_schedule
        ]
    else:
        daily_schedule = []

    # Serialize list fields (weeklyRoadmap, recommendedProjects, etc.)
    def _str_list(key: str) -> List[str]:
        raw = source.get(key, None)
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return []

    return {
        "dailySchedule": daily_schedule,
        "weeklyRoadmap": _str_list("weeklyRoadmap"),
        "recommendedProjects": _str_list("recommendedProjects"),
        "certificationRecommendations": _str_list("certificationRecommendations"),
        "estimatedCompletionTimeline": _coerce_string(
            source.get("estimatedCompletionTimeline", None)
        ),
    }


def _serialize_schedule_entry(entry: Any) -> dict:
    """
    Project a single daily schedule entry to the four fields expected by the
    Bedrock prompt contract, applying defaults for any missing or None values.

    The ``date`` field present in DynamoDB records is intentionally excluded
    from the output.

    Args:
        entry: A dict representing one day in the DynamoDB ``dailySchedule``
               list.  Non-dict values are treated as empty.

    Returns:
        A dict with exactly the keys: ``day``, ``resourceId``,
        ``estimatedDuration``, ``recommendationReason``.
    """
    src: dict = entry if isinstance(entry, dict) else {}

    # Coerce 'day' to an integer
    raw_day = src.get("day", None)
    if raw_day is None:
        day_val: Any = _DAILY_SCHEDULE_DEFAULTS["day"]
    elif isinstance(raw_day, (int, float)):
        day_val = int(raw_day)
    else:
        try:
            day_val = int(raw_day)
        except (TypeError, ValueError):
            day_val = _DAILY_SCHEDULE_DEFAULTS["day"]

    return {
        "day": day_val,
        "resourceId": _coerce_string(src.get("resourceId", None)),
        "estimatedDuration": _coerce_string(src.get("estimatedDuration", None)),
        "recommendationReason": _coerce_string(src.get("recommendationReason", None)),
    }


def _coerce_string(value: Any, default: str = "") -> str:
    """
    Coerce a value to a string, returning *default* when the value is None.

    Args:
        value:   The raw value (may be None or a non-string type).
        default: Fallback returned when *value* is None.

    Returns:
        A string representation of *value*, or *default* if *value* is None.
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return default


def _coerce_ai_field(key: str, value: Any) -> Any:
    """
    Coerce a single AI metadata field value to its expected type.

    If the stored value is ``None`` or of an unexpected type the field-level
    default is returned, ensuring the serialized output is always valid for
    inclusion in a Bedrock prompt.

    Args:
        key:   The AI metadata field name.
        value: The raw value from DynamoDB (may be None or wrong type).

    Returns:
        A type-safe value appropriate for the Bedrock prompt contract.
    """
    default = _AI_METADATA_DEFAULTS[key]

    if value is None:
        return default

    # priorityScore and recommendedWeek must be numbers
    if key in ("priorityScore", "recommendedWeek"):
        if isinstance(value, (int, float)):
            return value
        try:
            # Attempt numeric coercion (e.g. Decimal from DynamoDB)
            return int(value)
        except (TypeError, ValueError):
            return default

    # skills must be a list of strings
    if key == "skills":
        if isinstance(value, list):
            return [str(item) for item in value]
        return default

    # All remaining fields (summary, difficulty, estimatedTime, whyLearnNow)
    # must be strings
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return default
