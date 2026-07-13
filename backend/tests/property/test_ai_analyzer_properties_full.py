"""
Property-based tests for AI_Analyzer Lambda (Properties 6, 7, 8).

# Feature: learningpath-ai, Property 6: AI metadata fields populated after analysis
# Feature: learningpath-ai, Property 7: AI metadata prompt always contains required keys
# Feature: learningpath-ai, Property 8: Bedrock error preserves original resource record

Validates: Requirements 2.2, 2.3, 2.4, 2.5
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.ai_analyzer.handler import (
    REQUIRED_AI_FIELDS,
    build_bedrock_prompt,
    merge_ai_metadata,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

non_empty_text = st.text(min_size=1, max_size=100)
skills_strategy = st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5)

def resource_strategy():
    return st.fixed_dictionaries({
        "userId": st.text(min_size=1, max_size=50),
        "resourceId": st.text(min_size=1, max_size=80).map(lambda s: f"RESOURCE#{s}"),
        "title": non_empty_text,
        "url": st.text(min_size=5, max_size=200).map(lambda s: "https://" + s),
        "resourceType": st.sampled_from([
            "Technical Article", "Documentation", "YouTube Video",
            "Online Course", "PDF", "GitHub Repository",
        ]),
        "technology": st.text(max_size=50),
        "description": st.text(max_size=200),
        "learningStatus": st.just("Not Started"),
        "aiMetadata": st.none(),
        "createdAt": st.just("2024-01-01T00:00:00+00:00"),
        "updatedAt": st.just("2024-01-01T00:00:00+00:00"),
    })

def valid_ai_metadata_strategy():
    return st.fixed_dictionaries({
        "priorityScore": st.integers(min_value=0, max_value=100),
        "summary": st.text(min_size=0, max_size=200),
        "skills": skills_strategy,
        "difficulty": st.sampled_from(["Beginner", "Intermediate", "Advanced"]),
        "estimatedTime": st.text(max_size=50),
        "whyLearnNow": st.text(max_size=200),
        "recommendedWeek": st.integers(min_value=0, max_value=52),
    })

def _make_db_with_resource(resource):
    db = MagicMock()
    store = {(resource["userId"], resource["resourceId"]): dict(resource)}

    def get_item(Key):
        item = store.get((Key["userId"], Key["resourceId"]))
        return {"Item": dict(item)} if item else {}

    def put_item(Item):
        store[(Item["userId"], Item["resourceId"])] = dict(Item)
        return {}

    db.get_item.side_effect = get_item
    db.put_item.side_effect = put_item
    db._store = store
    return db


# ---------------------------------------------------------------------------
# Property 6: AI metadata fields populated after analysis
# ---------------------------------------------------------------------------

@given(resource=resource_strategy(), ai_metadata=valid_ai_metadata_strategy())
@settings(max_examples=100)
def test_property6_all_required_ai_fields_populated_after_merge(resource, ai_metadata):
    """
    # Feature: learningpath-ai, Property 6: AI metadata fields populated after analysis

    For any resource and any valid Bedrock JSON response, after merging AI
    metadata the stored record must contain non-null values for all required
    AI metadata fields.

    Validates: Requirements 2.2, 2.4
    """
    db = _make_db_with_resource(resource)
    merge_ai_metadata(resource["userId"], resource["resourceId"], ai_metadata, db)

    saved = db._store[(resource["userId"], resource["resourceId"])]
    assert saved["aiMetadata"] is not None, "aiMetadata should not be null after successful analysis"

    for field in REQUIRED_AI_FIELDS:
        assert field in saved["aiMetadata"], f"Missing required AI field: {field}"


@given(resource=resource_strategy(), ai_metadata=valid_ai_metadata_strategy())
@settings(max_examples=100)
def test_property6_ai_metadata_values_match_bedrock_response(resource, ai_metadata):
    """
    # Feature: learningpath-ai, Property 6: AI metadata fields populated after analysis

    The merged AI metadata values must match the values from the Bedrock response.

    Validates: Requirements 2.2, 2.4
    """
    db = _make_db_with_resource(resource)
    merge_ai_metadata(resource["userId"], resource["resourceId"], ai_metadata, db)

    saved = db._store[(resource["userId"], resource["resourceId"])]
    for field in REQUIRED_AI_FIELDS:
        assert saved["aiMetadata"][field] == ai_metadata.get(field), (
            f"Field '{field}' mismatch: expected {ai_metadata.get(field)!r}, "
            f"got {saved['aiMetadata'][field]!r}"
        )


# ---------------------------------------------------------------------------
# Property 7: AI metadata prompt always contains required keys
# ---------------------------------------------------------------------------

@given(resource=resource_strategy())
@settings(max_examples=100)
def test_property7_prompt_always_contains_all_required_keys(resource):
    """
    # Feature: learningpath-ai, Property 7: AI metadata prompt always contains required keys

    For any resource input, the prompt construction function must always produce
    a string containing all required Bedrock response keys.

    Validates: Requirements 2.3
    """
    prompt = build_bedrock_prompt(resource)

    assert isinstance(prompt, str), "Prompt must be a string"
    assert len(prompt) > 0, "Prompt must not be empty"

    for key in REQUIRED_AI_FIELDS:
        assert key in prompt, (
            f"Required Bedrock response key '{key}' not found in prompt"
        )


@given(resource=resource_strategy())
@settings(max_examples=100)
def test_property7_prompt_contains_resource_title_and_url(resource):
    """
    # Feature: learningpath-ai, Property 7: AI metadata prompt always contains required keys

    The prompt must always include the resource title and URL so Bedrock
    has the necessary context to analyze it.

    Validates: Requirements 2.3
    """
    prompt = build_bedrock_prompt(resource)
    assert resource["title"] in prompt, "Prompt must include the resource title"
    assert resource["url"] in prompt, "Prompt must include the resource URL"


@given(resource=resource_strategy())
@settings(max_examples=100)
def test_property7_prompt_requests_json_format(resource):
    """
    # Feature: learningpath-ai, Property 7: AI metadata prompt always contains required keys

    The prompt must always explicitly request a JSON-formatted response.

    Validates: Requirements 2.3
    """
    prompt = build_bedrock_prompt(resource)
    prompt_lower = prompt.lower()
    assert "json" in prompt_lower, "Prompt must request a JSON response"


# ---------------------------------------------------------------------------
# Property 8: Bedrock error preserves original resource record
# ---------------------------------------------------------------------------

@given(resource=resource_strategy())
@settings(max_examples=100)
def test_property8_original_fields_intact_when_bedrock_returns_none(resource):
    """
    # Feature: learningpath-ai, Property 8: Bedrock error preserves original resource record

    When Bedrock returns an error (ai_metadata=None), the resource record
    must remain in DynamoDB with all original user-supplied fields intact.

    Validates: Requirements 2.5
    """
    db = _make_db_with_resource(resource)
    merge_ai_metadata(resource["userId"], resource["resourceId"], None, db)

    saved = db._store[(resource["userId"], resource["resourceId"])]

    # All original user fields must be preserved
    for field in ("title", "url", "resourceType", "userId", "resourceId"):
        assert saved[field] == resource[field], (
            f"Field '{field}' was modified: expected {resource[field]!r}, "
            f"got {saved[field]!r}"
        )


@given(resource=resource_strategy())
@settings(max_examples=100)
def test_property8_ai_metadata_is_null_when_bedrock_fails(resource):
    """
    # Feature: learningpath-ai, Property 8: Bedrock error preserves original resource record

    When Bedrock fails, the aiMetadata field in the stored record must be null.

    Validates: Requirements 2.5
    """
    db = _make_db_with_resource(resource)
    merge_ai_metadata(resource["userId"], resource["resourceId"], None, db)

    saved = db._store[(resource["userId"], resource["resourceId"])]
    assert saved["aiMetadata"] is None, (
        f"aiMetadata should be null on Bedrock failure, got: {saved['aiMetadata']!r}"
    )


@given(resource=resource_strategy())
@settings(max_examples=100)
def test_property8_resource_still_exists_after_bedrock_failure(resource):
    """
    # Feature: learningpath-ai, Property 8: Bedrock error preserves original resource record

    The resource record must still exist in DynamoDB after a Bedrock failure —
    it must not be deleted or left in an inconsistent state.

    Validates: Requirements 2.5
    """
    db = _make_db_with_resource(resource)
    merge_ai_metadata(resource["userId"], resource["resourceId"], None, db)

    key = (resource["userId"], resource["resourceId"])
    assert key in db._store, "Resource must still exist in DynamoDB after Bedrock failure"
