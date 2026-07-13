"""
Unit tests for backend/shared/pretty_printer.py — AI metadata serialization.

Validates serialize_ai_metadata() against:
  - Requirement 2.7 / Property 9: round-trip serialization of AI metadata into
    the exact JSON structure accepted by the Bedrock prompt.

Note: Property-based tests for Property 9 are in
      backend/tests/property/test_ai_analyzer_properties.py (task 2.7).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.pretty_printer import (
    AI_METADATA_KEYS,
    _AI_METADATA_DEFAULTS,
    serialize_ai_metadata,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BEDROCK_PROMPT_KEYS = set(AI_METADATA_KEYS)

_FULL_METADATA: dict = {
    "priorityScore": 85,
    "summary": "Introduction to Amazon EC2",
    "skills": ["AWS", "EC2", "Cloud Computing"],
    "difficulty": "Intermediate",
    "estimatedTime": "2 hours",
    "whyLearnNow": "EC2 is the core compute service needed for your AWS Cloud Engineer goal.",
    "recommendedWeek": 2,
}


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """The serialized output always contains exactly the Bedrock prompt keys."""

    def test_output_has_all_required_keys(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        assert set(result.keys()) == BEDROCK_PROMPT_KEYS

    def test_output_key_count_matches_prompt_contract(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        assert len(result) == len(AI_METADATA_KEYS)

    def test_output_key_order_matches_prompt_contract(self):
        """Keys should come out in the canonical order defined by AI_METADATA_KEYS."""
        result = serialize_ai_metadata(_FULL_METADATA)
        assert list(result.keys()) == list(AI_METADATA_KEYS)

    def test_no_extra_keys_in_output(self):
        metadata_with_extra = {**_FULL_METADATA, "extraField": "ignored"}
        result = serialize_ai_metadata(metadata_with_extra)
        assert "extraField" not in result
        assert set(result.keys()) == BEDROCK_PROMPT_KEYS


# ---------------------------------------------------------------------------
# Round-trip correctness (Property 9)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Serializing a complete AI metadata record yields back the same values."""

    def test_full_metadata_round_trip(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        assert result["priorityScore"] == 85
        assert result["summary"] == "Introduction to Amazon EC2"
        assert result["skills"] == ["AWS", "EC2", "Cloud Computing"]
        assert result["difficulty"] == "Intermediate"
        assert result["estimatedTime"] == "2 hours"
        assert result["whyLearnNow"] == "EC2 is the core compute service needed for your AWS Cloud Engineer goal."
        assert result["recommendedWeek"] == 2

    def test_priority_score_zero_preserved(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "priorityScore": 0})
        assert result["priorityScore"] == 0

    def test_priority_score_max_preserved(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "priorityScore": 100})
        assert result["priorityScore"] == 100

    def test_recommended_week_zero_preserved(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "recommendedWeek": 0})
        assert result["recommendedWeek"] == 0

    def test_empty_skills_list_preserved(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "skills": []})
        assert result["skills"] == []

    def test_single_skill_preserved(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "skills": ["Python"]})
        assert result["skills"] == ["Python"]

    def test_empty_strings_preserved(self):
        result = serialize_ai_metadata({
            **_FULL_METADATA,
            "summary": "",
            "difficulty": "",
            "estimatedTime": "",
            "whyLearnNow": "",
        })
        assert result["summary"] == ""
        assert result["difficulty"] == ""
        assert result["estimatedTime"] == ""
        assert result["whyLearnNow"] == ""


# ---------------------------------------------------------------------------
# None / missing field handling
# ---------------------------------------------------------------------------


class TestNoneAndMissingFields:
    """Missing or None fields are replaced with appropriate defaults."""

    def test_none_input_returns_all_defaults(self):
        result = serialize_ai_metadata(None)
        assert result["priorityScore"] == 0
        assert result["summary"] == ""
        assert result["skills"] == []
        assert result["difficulty"] == ""
        assert result["estimatedTime"] == ""
        assert result["whyLearnNow"] == ""
        assert result["recommendedWeek"] == 0

    def test_empty_dict_returns_all_defaults(self):
        result = serialize_ai_metadata({})
        assert result == dict(_AI_METADATA_DEFAULTS)

    def test_none_priority_score_defaults_to_zero(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "priorityScore": None})
        assert result["priorityScore"] == 0

    def test_none_recommended_week_defaults_to_zero(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "recommendedWeek": None})
        assert result["recommendedWeek"] == 0

    def test_none_summary_defaults_to_empty_string(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "summary": None})
        assert result["summary"] == ""

    def test_none_skills_defaults_to_empty_list(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "skills": None})
        assert result["skills"] == []

    def test_none_difficulty_defaults_to_empty_string(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "difficulty": None})
        assert result["difficulty"] == ""

    def test_none_estimated_time_defaults_to_empty_string(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "estimatedTime": None})
        assert result["estimatedTime"] == ""

    def test_none_why_learn_now_defaults_to_empty_string(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "whyLearnNow": None})
        assert result["whyLearnNow"] == ""

    def test_missing_priority_score_defaults_to_zero(self):
        partial = {k: v for k, v in _FULL_METADATA.items() if k != "priorityScore"}
        result = serialize_ai_metadata(partial)
        assert result["priorityScore"] == 0

    def test_missing_skills_defaults_to_empty_list(self):
        partial = {k: v for k, v in _FULL_METADATA.items() if k != "skills"}
        result = serialize_ai_metadata(partial)
        assert result["skills"] == []

    def test_missing_recommended_week_defaults_to_zero(self):
        partial = {k: v for k, v in _FULL_METADATA.items() if k != "recommendedWeek"}
        result = serialize_ai_metadata(partial)
        assert result["recommendedWeek"] == 0


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


class TestTypeCoercion:
    """Fields with unexpected types are coerced or defaulted appropriately."""

    def test_decimal_priority_score_coerced_to_int(self):
        """DynamoDB Decimal type must be coerced to int."""
        from decimal import Decimal
        result = serialize_ai_metadata({**_FULL_METADATA, "priorityScore": Decimal("72")})
        assert result["priorityScore"] == 72
        assert isinstance(result["priorityScore"], int)

    def test_decimal_recommended_week_coerced_to_int(self):
        from decimal import Decimal
        result = serialize_ai_metadata({**_FULL_METADATA, "recommendedWeek": Decimal("3")})
        assert result["recommendedWeek"] == 3

    def test_float_priority_score_preserved(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "priorityScore": 72.5})
        assert result["priorityScore"] == 72.5

    def test_skills_items_coerced_to_strings(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "skills": [1, 2, "three"]})
        assert result["skills"] == ["1", "2", "three"]

    def test_non_list_skills_returns_default(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "skills": "AWS"})
        assert result["skills"] == []

    def test_non_string_summary_coerced_to_string(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "summary": 42})
        assert result["summary"] == "42"

    def test_non_string_difficulty_coerced_to_string(self):
        result = serialize_ai_metadata({**_FULL_METADATA, "difficulty": 3})
        assert result["difficulty"] == "3"

    def test_non_dict_input_treated_as_empty(self):
        """A non-dict input (e.g. a list) should behave like an empty dict."""
        result = serialize_ai_metadata([])  # type: ignore[arg-type]
        assert result == dict(_AI_METADATA_DEFAULTS)

    def test_string_input_treated_as_empty(self):
        result = serialize_ai_metadata("invalid")  # type: ignore[arg-type]
        assert result == dict(_AI_METADATA_DEFAULTS)


# ---------------------------------------------------------------------------
# Valid Bedrock prompt inclusion
# ---------------------------------------------------------------------------


class TestBedrockPromptValidity:
    """Serialized output can be used directly in a Bedrock prompt payload."""

    def test_output_is_json_serializable(self):
        import json
        result = serialize_ai_metadata(_FULL_METADATA)
        # Should not raise
        serialized = json.dumps(result)
        parsed = json.loads(serialized)
        assert parsed == result

    def test_output_with_defaults_is_json_serializable(self):
        import json
        result = serialize_ai_metadata(None)
        serialized = json.dumps(result)
        parsed = json.loads(serialized)
        assert parsed == result

    def test_priority_score_is_numeric(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        assert isinstance(result["priorityScore"], (int, float))

    def test_recommended_week_is_numeric(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        assert isinstance(result["recommendedWeek"], (int, float))

    def test_skills_is_list(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        assert isinstance(result["skills"], list)

    def test_string_fields_are_strings(self):
        result = serialize_ai_metadata(_FULL_METADATA)
        for key in ("summary", "difficulty", "estimatedTime", "whyLearnNow"):
            assert isinstance(result[key], str), f"{key} should be a string"


# ===========================================================================
# Tests for serialize_learning_plan (Property 15 / Requirement 4.10)
# ===========================================================================

from shared.pretty_printer import (
    DAILY_SCHEDULE_KEYS,
    LEARNING_PLAN_KEYS,
    _LEARNING_PLAN_DEFAULTS,
    serialize_learning_plan,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

#: A complete DynamoDB Learning_Plan record (mirrors the schema in design.md)
_FULL_PLAN: dict = {
    "userId": "user-42",
    "resourceId": "PLAN#active",
    "dailySchedule": [
        {
            "day": 1,
            "date": "2024-01-15",
            "resourceId": "RESOURCE#abc",
            "estimatedDuration": "1 hour",
            "recommendationReason": "Foundations first",
        },
        {
            "day": 2,
            "date": "2024-01-16",
            "resourceId": "RESOURCE#def",
            "estimatedDuration": "30 minutes",
            "recommendationReason": "Build on day 1",
        },
    ],
    "weeklyRoadmap": ["Week 1: AWS basics", "Week 2: Compute"],
    "recommendedProjects": ["Deploy a static S3 site"],
    "certificationRecommendations": ["AWS SAA"],
    "estimatedCompletionTimeline": "3 months",
    "generatedAt": "2024-01-15T00:00:00Z",
    "careerGoalSnapshot": {"careerGoal": "Become AWS Cloud Engineer"},
}

#: Expected Bedrock prompt keys for the top-level structure
_BEDROCK_PLAN_KEYS = set(LEARNING_PLAN_KEYS)

#: Expected Bedrock prompt keys for each daily-schedule entry
_BEDROCK_ENTRY_KEYS = set(DAILY_SCHEDULE_KEYS)


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


class TestLearningPlanOutputStructure:
    """Serialized plan always contains exactly the Bedrock prompt top-level keys."""

    def test_output_has_all_required_keys(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert set(result.keys()) == _BEDROCK_PLAN_KEYS

    def test_no_extra_keys_in_output(self):
        """DynamoDB-only fields (userId, resourceId, generatedAt, …) are excluded."""
        result = serialize_learning_plan(_FULL_PLAN)
        for dynamo_only in ("userId", "resourceId", "generatedAt", "careerGoalSnapshot"):
            assert dynamo_only not in result

    def test_key_order_matches_prompt_contract(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert list(result.keys()) == list(LEARNING_PLAN_KEYS)

    def test_daily_schedule_entry_has_exactly_prompt_keys(self):
        result = serialize_learning_plan(_FULL_PLAN)
        for entry in result["dailySchedule"]:
            assert set(entry.keys()) == _BEDROCK_ENTRY_KEYS

    def test_date_field_stripped_from_schedule_entries(self):
        """The 'date' field stored in DynamoDB must NOT appear in the Bedrock output."""
        result = serialize_learning_plan(_FULL_PLAN)
        for entry in result["dailySchedule"]:
            assert "date" not in entry


# ---------------------------------------------------------------------------
# Round-trip correctness (Property 15)
# ---------------------------------------------------------------------------


class TestLearningPlanRoundTrip:
    """Serializing a complete Learning_Plan preserves all prompt-contract values."""

    def test_daily_schedule_values_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        first = result["dailySchedule"][0]
        assert first["day"] == 1
        assert first["resourceId"] == "RESOURCE#abc"
        assert first["estimatedDuration"] == "1 hour"
        assert first["recommendationReason"] == "Foundations first"

    def test_second_day_values_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        second = result["dailySchedule"][1]
        assert second["day"] == 2
        assert second["resourceId"] == "RESOURCE#def"
        assert second["estimatedDuration"] == "30 minutes"
        assert second["recommendationReason"] == "Build on day 1"

    def test_weekly_roadmap_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert result["weeklyRoadmap"] == ["Week 1: AWS basics", "Week 2: Compute"]

    def test_recommended_projects_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert result["recommendedProjects"] == ["Deploy a static S3 site"]

    def test_certification_recommendations_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert result["certificationRecommendations"] == ["AWS SAA"]

    def test_estimated_completion_timeline_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert result["estimatedCompletionTimeline"] == "3 months"

    def test_schedule_entry_count_preserved(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert len(result["dailySchedule"]) == 2


# ---------------------------------------------------------------------------
# None / missing field handling
# ---------------------------------------------------------------------------


class TestLearningPlanNoneAndMissingFields:
    """Missing or None fields produce appropriate defaults."""

    def test_none_input_returns_empty_defaults(self):
        result = serialize_learning_plan(None)
        assert result["dailySchedule"] == []
        assert result["weeklyRoadmap"] == []
        assert result["recommendedProjects"] == []
        assert result["certificationRecommendations"] == []
        assert result["estimatedCompletionTimeline"] == ""

    def test_empty_dict_returns_defaults(self):
        result = serialize_learning_plan({})
        assert result["dailySchedule"] == []
        assert result["weeklyRoadmap"] == []
        assert result["estimatedCompletionTimeline"] == ""

    def test_none_daily_schedule_returns_empty_list(self):
        plan = {**_FULL_PLAN, "dailySchedule": None}
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"] == []

    def test_none_weekly_roadmap_returns_empty_list(self):
        plan = {**_FULL_PLAN, "weeklyRoadmap": None}
        result = serialize_learning_plan(plan)
        assert result["weeklyRoadmap"] == []

    def test_none_recommended_projects_returns_empty_list(self):
        plan = {**_FULL_PLAN, "recommendedProjects": None}
        result = serialize_learning_plan(plan)
        assert result["recommendedProjects"] == []

    def test_none_certification_recommendations_returns_empty_list(self):
        plan = {**_FULL_PLAN, "certificationRecommendations": None}
        result = serialize_learning_plan(plan)
        assert result["certificationRecommendations"] == []

    def test_none_timeline_returns_empty_string(self):
        plan = {**_FULL_PLAN, "estimatedCompletionTimeline": None}
        result = serialize_learning_plan(plan)
        assert result["estimatedCompletionTimeline"] == ""

    def test_missing_timeline_returns_empty_string(self):
        plan = {k: v for k, v in _FULL_PLAN.items() if k != "estimatedCompletionTimeline"}
        result = serialize_learning_plan(plan)
        assert result["estimatedCompletionTimeline"] == ""

    def test_schedule_entry_missing_resource_id_defaults_to_empty_string(self):
        plan = {
            **_FULL_PLAN,
            "dailySchedule": [{"day": 1, "estimatedDuration": "1 hour", "recommendationReason": "test"}],
        }
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"][0]["resourceId"] == ""

    def test_schedule_entry_none_recommendation_reason_defaults_to_empty_string(self):
        plan = {
            **_FULL_PLAN,
            "dailySchedule": [
                {"day": 1, "resourceId": "R#x", "estimatedDuration": "1 hour", "recommendationReason": None}
            ],
        }
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"][0]["recommendationReason"] == ""

    def test_empty_daily_schedule_list_preserved(self):
        plan = {**_FULL_PLAN, "dailySchedule": []}
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"] == []

    def test_non_dict_entry_in_schedule_uses_defaults(self):
        plan = {**_FULL_PLAN, "dailySchedule": ["not-a-dict"]}
        result = serialize_learning_plan(plan)
        entry = result["dailySchedule"][0]
        assert entry["resourceId"] == ""
        assert entry["estimatedDuration"] == ""
        assert entry["recommendationReason"] == ""
        assert entry["day"] == 1


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


class TestLearningPlanTypeCoercion:
    """Field values with unexpected types are coerced or defaulted."""

    def test_decimal_day_coerced_to_int(self):
        from decimal import Decimal
        plan = {
            **_FULL_PLAN,
            "dailySchedule": [
                {"day": Decimal("3"), "resourceId": "R#x", "estimatedDuration": "1h", "recommendationReason": "r"}
            ],
        }
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"][0]["day"] == 3
        assert isinstance(result["dailySchedule"][0]["day"], int)

    def test_float_day_coerced_to_int(self):
        plan = {
            **_FULL_PLAN,
            "dailySchedule": [
                {"day": 5.0, "resourceId": "R#x", "estimatedDuration": "1h", "recommendationReason": "r"}
            ],
        }
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"][0]["day"] == 5

    def test_non_string_timeline_coerced_to_string(self):
        plan = {**_FULL_PLAN, "estimatedCompletionTimeline": 90}
        result = serialize_learning_plan(plan)
        assert result["estimatedCompletionTimeline"] == "90"

    def test_list_items_in_roadmap_coerced_to_strings(self):
        plan = {**_FULL_PLAN, "weeklyRoadmap": [1, 2, "three"]}
        result = serialize_learning_plan(plan)
        assert result["weeklyRoadmap"] == ["1", "2", "three"]

    def test_non_list_daily_schedule_treated_as_empty(self):
        plan = {**_FULL_PLAN, "dailySchedule": "not-a-list"}
        result = serialize_learning_plan(plan)
        assert result["dailySchedule"] == []

    def test_non_list_weekly_roadmap_treated_as_empty(self):
        plan = {**_FULL_PLAN, "weeklyRoadmap": "single roadmap item"}
        result = serialize_learning_plan(plan)
        assert result["weeklyRoadmap"] == []

    def test_non_dict_input_treated_as_empty(self):
        result = serialize_learning_plan([])  # type: ignore[arg-type]
        assert result["dailySchedule"] == []
        assert result["weeklyRoadmap"] == []
        assert result["estimatedCompletionTimeline"] == ""


# ---------------------------------------------------------------------------
# Valid Bedrock prompt inclusion
# ---------------------------------------------------------------------------


class TestLearningPlanBedrockPromptValidity:
    """Serialized output can be embedded directly in a Bedrock prompt payload."""

    def test_output_is_json_serializable(self):
        import json
        result = serialize_learning_plan(_FULL_PLAN)
        serialized = json.dumps(result)
        parsed = json.loads(serialized)
        assert parsed == result

    def test_default_output_is_json_serializable(self):
        import json
        result = serialize_learning_plan(None)
        serialized = json.dumps(result)
        parsed = json.loads(serialized)
        assert parsed == result

    def test_daily_schedule_is_list(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert isinstance(result["dailySchedule"], list)

    def test_weekly_roadmap_is_list_of_strings(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert isinstance(result["weeklyRoadmap"], list)
        for item in result["weeklyRoadmap"]:
            assert isinstance(item, str)

    def test_schedule_entry_day_is_int(self):
        result = serialize_learning_plan(_FULL_PLAN)
        for entry in result["dailySchedule"]:
            assert isinstance(entry["day"], int)

    def test_schedule_entry_string_fields_are_strings(self):
        result = serialize_learning_plan(_FULL_PLAN)
        for entry in result["dailySchedule"]:
            for key in ("resourceId", "estimatedDuration", "recommendationReason"):
                assert isinstance(entry[key], str), f"{key} should be a string"

    def test_timeline_is_string(self):
        result = serialize_learning_plan(_FULL_PLAN)
        assert isinstance(result["estimatedCompletionTimeline"], str)

    def test_large_schedule_serializes_correctly(self):
        """Verify a 14-day schedule round-trips without data loss."""
        import json
        schedule = [
            {
                "day": i,
                "date": f"2024-01-{i:02d}",
                "resourceId": f"RESOURCE#{i:03d}",
                "estimatedDuration": f"{i} hours",
                "recommendationReason": f"Reason for day {i}",
            }
            for i in range(1, 15)
        ]
        plan = {**_FULL_PLAN, "dailySchedule": schedule}
        result = serialize_learning_plan(plan)
        assert len(result["dailySchedule"]) == 14
        # All 'date' fields stripped
        for entry in result["dailySchedule"]:
            assert "date" not in entry
        # JSON round-trip
        assert json.loads(json.dumps(result)) == result
