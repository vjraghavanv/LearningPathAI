"""
Property-based tests for Pretty_Printer AI metadata serialization (Property 9).

# Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

Validates: Requirements 2.7
"""

import json
import os
import sys

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.pretty_printer import (
    AI_METADATA_KEYS,
    serialize_ai_metadata,
)

# ---------------------------------------------------------------------------
# Strategies for generating AI metadata
# ---------------------------------------------------------------------------

# Strategy for valid priorityScore in [0, 100]
priority_score_strategy = st.integers(min_value=0, max_value=100)

# Strategy for recommendedWeek (non-negative integer)
recommended_week_strategy = st.integers(min_value=0, max_value=52)

# Strategy for skill strings
skill_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters=" +-#.",
    ),
    min_size=1,
    max_size=50,
)

# Strategy for list of skills
skills_strategy = st.lists(skill_strategy, min_size=0, max_size=10)

# Strategy for non-empty text fields
text_field_strategy = st.text(min_size=0, max_size=200)


def ai_metadata_strategy():
    """Generate arbitrary valid AI metadata dicts with all required keys."""
    return st.fixed_dictionaries(
        {
            "priorityScore": priority_score_strategy,
            "summary": text_field_strategy,
            "skills": skills_strategy,
            "difficulty": st.sampled_from(
                ["Beginner", "Intermediate", "Advanced", ""]
            ),
            "estimatedTime": text_field_strategy,
            "whyLearnNow": text_field_strategy,
            "recommendedWeek": recommended_week_strategy,
        }
    )


# ---------------------------------------------------------------------------
# Property 9: AI metadata serialization round-trip
#
# Feature: learningpath-ai, Property 9: AI metadata serialization round-trip
# ---------------------------------------------------------------------------


@given(ai_metadata=ai_metadata_strategy())
@settings(max_examples=100)
def test_property9_output_contains_all_required_bedrock_keys(ai_metadata):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any valid AI metadata dict, serialize_ai_metadata must return a dict
    containing exactly all the required Bedrock prompt keys.

    Validates: Requirements 2.7
    """
    result = serialize_ai_metadata(ai_metadata)
    assert set(result.keys()) == set(AI_METADATA_KEYS), (
        f"Output keys {set(result.keys())} do not match required Bedrock keys {set(AI_METADATA_KEYS)}"
    )


@given(ai_metadata=ai_metadata_strategy())
@settings(max_examples=100)
def test_property9_output_values_match_input_for_valid_fields(ai_metadata):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any valid AI metadata dict, the output values must match the input
    values for all fields (string fields, skills list, numeric fields).

    Validates: Requirements 2.7
    """
    result = serialize_ai_metadata(ai_metadata)

    # Numeric fields should be preserved exactly
    assert result["priorityScore"] == ai_metadata["priorityScore"]
    assert result["recommendedWeek"] == ai_metadata["recommendedWeek"]

    # String fields should be preserved exactly
    assert result["summary"] == ai_metadata["summary"]
    assert result["difficulty"] == ai_metadata["difficulty"]
    assert result["estimatedTime"] == ai_metadata["estimatedTime"]
    assert result["whyLearnNow"] == ai_metadata["whyLearnNow"]

    # Skills list should be preserved (as strings)
    assert result["skills"] == [str(s) for s in ai_metadata["skills"]]


@given(ai_metadata=ai_metadata_strategy())
@settings(max_examples=100)
def test_property9_json_round_trip(ai_metadata):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any valid AI metadata dict, json.dumps(serialize_ai_metadata(input))
    must be parseable back to a JSON object equivalent to the serialized output.

    Validates: Requirements 2.7
    """
    result = serialize_ai_metadata(ai_metadata)
    serialized = json.dumps(result)
    parsed = json.loads(serialized)
    assert parsed == result, (
        f"Round-trip failed: json.loads(json.dumps(result)) != result"
    )


@given(ai_metadata=ai_metadata_strategy())
@settings(max_examples=100)
def test_property9_priority_score_in_valid_range(ai_metadata):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any AI metadata with priorityScore in [0, 100], the serialized output
    must also have priorityScore in [0, 100].

    Validates: Requirements 2.7
    """
    # ai_metadata_strategy already constrains priorityScore to [0, 100]
    assume(0 <= ai_metadata["priorityScore"] <= 100)
    result = serialize_ai_metadata(ai_metadata)
    assert 0 <= result["priorityScore"] <= 100, (
        f"priorityScore {result['priorityScore']} is out of range [0, 100]"
    )


@given(ai_metadata=ai_metadata_strategy())
@settings(max_examples=100)
def test_property9_skills_is_always_list_of_strings(ai_metadata):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any valid AI metadata dict, the serialized output's 'skills' field
    must always be a list of strings.

    Validates: Requirements 2.7
    """
    result = serialize_ai_metadata(ai_metadata)
    assert isinstance(result["skills"], list), (
        f"skills must be a list, got {type(result['skills'])}"
    )
    for item in result["skills"]:
        assert isinstance(item, str), (
            f"Each skill must be a string, got {type(item)}: {item!r}"
        )


@given(ai_metadata=ai_metadata_strategy())
@settings(max_examples=100)
def test_property9_all_string_fields_are_strings(ai_metadata):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any valid AI metadata dict, all string fields in the serialized output
    (summary, difficulty, estimatedTime, whyLearnNow) must be actual strings.

    Validates: Requirements 2.7
    """
    result = serialize_ai_metadata(ai_metadata)
    string_fields = ("summary", "difficulty", "estimatedTime", "whyLearnNow")
    for field in string_fields:
        assert isinstance(result[field], str), (
            f"Field '{field}' must be a str, got {type(result[field])}: {result[field]!r}"
        )


@given(
    ai_metadata=ai_metadata_strategy(),
    extra_key=st.text(min_size=1, max_size=20).filter(
        lambda k: k not in AI_METADATA_KEYS
    ),
    extra_value=st.text(),
)
@settings(max_examples=100)
def test_property9_extra_keys_are_stripped(ai_metadata, extra_key, extra_value):
    """
    # Feature: learningpath-ai, Property 9: AI metadata serialization round-trip

    For any AI metadata dict containing extra keys beyond the Bedrock contract,
    the serialized output must not include those extra keys.

    Validates: Requirements 2.7
    """
    metadata_with_extra = {**ai_metadata, extra_key: extra_value}
    result = serialize_ai_metadata(metadata_with_extra)
    assert extra_key not in result, (
        f"Extra key '{extra_key}' should not appear in serialized output"
    )
    assert set(result.keys()) == set(AI_METADATA_KEYS)
