"""
Property-based tests for SearchService Lambda (Properties 22–23).

# Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic
# Feature: learningpath-ai, Property 23: Search with unrecognized filter key returns HTTP 400

Validates: Requirements 8.1–8.6
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.search_service.handler import (
    SUPPORTED_FILTER_KEYS,
    _resource_matches,
    handle_search,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_user_id = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_",
    ),
)

_simple_text = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_ ",
    ),
).map(str.strip).filter(bool)

_technology_values = st.sampled_from(["AWS", "Python", "Docker", "Kubernetes", "React"])
_difficulty_values = st.sampled_from(["Beginner", "Intermediate", "Advanced"])
_resource_type_values = st.sampled_from([
    "Technical Article", "Documentation", "YouTube Video",
    "Online Course", "PDF", "GitHub Repository",
])
_tag_values = st.sampled_from(["aws-saa", "devops", "python", "docker", "react"])
_skill_values = st.sampled_from(["IAM", "EC2", "S3", "Lambda", "Python", "Docker"])


def _make_resource(
    user_id: str,
    resource_uuid: str,
    technology: str = "AWS",
    difficulty: str = "Beginner",
    resource_type: str = "Technical Article",
    tags: list[str] | None = None,
    skills: list[str] | None = None,
) -> dict:
    return {
        "userId": user_id,
        "resourceId": f"RESOURCE#{resource_uuid}",
        "title": f"Resource {resource_uuid[:8]}",
        "url": "https://example.com",
        "resourceType": resource_type,
        "difficulty": difficulty,
        "technology": technology,
        "tags": tags or [],
        "learningStatus": "Not Started",
        "completionTimestamp": None,
        "aiMetadata": {
            "skills": skills or [],
            "priorityScore": 50,
            "summary": "",
        },
    }


def _make_mock_db(resources: list[dict]) -> MagicMock:
    db = MagicMock()
    store = {(r["userId"], r["resourceId"]): r for r in resources}

    def query(**kwargs):
        return {"Items": list(store.values())}

    db.query.side_effect = query
    db._store = store
    return db


# ===========================================================================
# Property 22: Search returns all matching resources with AND logic
#
# Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic
# ===========================================================================


@given(
    user_id=_user_id,
    technology=_technology_values,
    n_matching=st.integers(min_value=0, max_value=5),
    n_non_matching=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_property22_technology_filter_returns_all_matching(
    user_id, technology, n_matching, n_non_matching
):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    For a technology filter, every resource with that technology must be returned
    and no resource with a different technology must appear.

    Validates: Requirements 8.1, 8.3
    """
    other_tech = "Python" if technology != "Python" else "AWS"

    matching = [
        _make_resource(user_id, f"match-{i}", technology=technology)
        for i in range(n_matching)
    ]
    non_matching = [
        _make_resource(user_id, f"non-{i}", technology=other_tech)
        for i in range(n_non_matching)
    ]

    db = _make_mock_db(matching + non_matching)
    result = handle_search(user_id, {"technology": technology}, db)

    assert result["statusCode"] == 200
    items = json.loads(result["body"])

    assert len(items) == n_matching, (
        f"Expected {n_matching} results for technology='{technology}', got {len(items)}"
    )
    for item in items:
        assert item["technology"].lower() == technology.lower()


@given(
    user_id=_user_id,
    difficulty=_difficulty_values,
    resource_type=_resource_type_values,
    n_both=st.integers(min_value=0, max_value=4),
    n_diff_only=st.integers(min_value=0, max_value=3),
    n_type_only=st.integers(min_value=0, max_value=3),
)
@settings(max_examples=100)
def test_property22_and_logic_difficulty_and_resource_type(
    user_id, difficulty, resource_type, n_both, n_diff_only, n_type_only
):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    When two filters are supplied, only resources matching BOTH must be returned.

    Validates: Requirements 8.3
    """
    other_diff = "Advanced" if difficulty != "Advanced" else "Beginner"
    other_type = "PDF" if resource_type != "PDF" else "Documentation"

    both_match = [
        _make_resource(user_id, f"both-{i}", difficulty=difficulty, resource_type=resource_type)
        for i in range(n_both)
    ]
    diff_only = [
        _make_resource(user_id, f"donly-{i}", difficulty=difficulty, resource_type=other_type)
        for i in range(n_diff_only)
    ]
    type_only = [
        _make_resource(user_id, f"tonly-{i}", difficulty=other_diff, resource_type=resource_type)
        for i in range(n_type_only)
    ]

    db = _make_mock_db(both_match + diff_only + type_only)
    result = handle_search(user_id, {"difficulty": difficulty, "resourceType": resource_type}, db)

    assert result["statusCode"] == 200
    items = json.loads(result["body"])

    assert len(items) == n_both, (
        f"AND-logic: expected {n_both} resources matching both filters, got {len(items)}"
    )


@given(user_id=_user_id)
@settings(max_examples=100)
def test_property22_no_filters_returns_all_resources(user_id):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    When no filters are supplied, all resources for the userId must be returned.

    Validates: Requirements 8.1
    """
    resources = [_make_resource(user_id, str(i)) for i in range(5)]
    db = _make_mock_db(resources)
    result = handle_search(user_id, {}, db)

    assert result["statusCode"] == 200
    items = json.loads(result["body"])
    assert len(items) == 5


@given(
    user_id=_user_id,
    technology=_technology_values,
)
@settings(max_examples=100)
def test_property22_no_match_returns_empty_list_200(user_id, technology):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    When no resources match, the response must be HTTP 200 with an empty list.

    Validates: Requirements 8.4
    """
    other_tech = "Python" if technology != "Python" else "AWS"
    resources = [_make_resource(user_id, f"r-{i}", technology=other_tech) for i in range(3)]
    db = _make_mock_db(resources)
    result = handle_search(user_id, {"technology": technology}, db)

    assert result["statusCode"] == 200
    items = json.loads(result["body"])
    assert items == [], f"Expected empty list, got {items}"


@given(
    user_id=_user_id,
    tag=_tag_values,
    n_with_tag=st.integers(min_value=1, max_value=5),
    n_without=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_property22_tag_filter_exact_match(user_id, tag, n_with_tag, n_without):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    Tag filter must return only resources that have the specified tag in their tags list.

    Validates: Requirements 8.2
    """
    other_tag = "unrelated-tag"
    tagged = [
        _make_resource(user_id, f"tagged-{i}", tags=[tag, "extra"])
        for i in range(n_with_tag)
    ]
    untagged = [
        _make_resource(user_id, f"untagged-{i}", tags=[other_tag])
        for i in range(n_without)
    ]

    db = _make_mock_db(tagged + untagged)
    result = handle_search(user_id, {"tag": tag}, db)

    assert result["statusCode"] == 200
    items = json.loads(result["body"])
    assert len(items) == n_with_tag


@given(
    user_id=_user_id,
    skill=_skill_values,
    n_with_skill=st.integers(min_value=1, max_value=5),
    n_without=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_property22_skill_tag_filter(user_id, skill, n_with_skill, n_without):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    skillTag filter must return only resources whose aiMetadata.skills contain the value.

    Validates: Requirements 8.2
    """
    skilled = [
        _make_resource(user_id, f"skill-{i}", skills=[skill, "Networking"])
        for i in range(n_with_skill)
    ]
    unskilled = [
        _make_resource(user_id, f"noskill-{i}", skills=["Unrelated"])
        for i in range(n_without)
    ]

    db = _make_mock_db(skilled + unskilled)
    result = handle_search(user_id, {"skillTag": skill.lower()}, db)

    assert result["statusCode"] == 200
    items = json.loads(result["body"])
    assert len(items) == n_with_skill


@given(
    user_id=_user_id,
    technology=_technology_values,
    difficulty=_difficulty_values,
    resource_type=_resource_type_values,
    n_all_match=st.integers(min_value=0, max_value=4),
)
@settings(max_examples=100)
def test_property22_three_filters_all_must_match(
    user_id, technology, difficulty, resource_type, n_all_match
):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    With three concurrent filters, only resources satisfying all three are returned.

    Validates: Requirements 8.3
    """
    other_diff = "Advanced" if difficulty != "Advanced" else "Beginner"

    all_match = [
        _make_resource(
            user_id, f"all-{i}",
            technology=technology, difficulty=difficulty, resource_type=resource_type,
        )
        for i in range(n_all_match)
    ]
    partial_match = [
        # Matches tech + type but wrong difficulty
        _make_resource(
            user_id, f"partial-{i}",
            technology=technology, difficulty=other_diff, resource_type=resource_type,
        )
        for i in range(2)
    ]

    db = _make_mock_db(all_match + partial_match)
    result = handle_search(
        user_id,
        {"technology": technology, "difficulty": difficulty, "resourceType": resource_type},
        db,
    )

    assert result["statusCode"] == 200
    items = json.loads(result["body"])
    assert len(items) == n_all_match, (
        f"Expected {n_all_match} with all 3 filters, got {len(items)}"
    )


@given(
    user_id=_user_id,
    n_resources=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=100)
def test_property22_result_is_subset_of_all_resources(user_id, n_resources):
    """
    # Feature: learningpath-ai, Property 22: Search returns all matching resources with AND logic

    Search results must always be a subset of the user's total resources.

    Validates: Requirements 8.1
    """
    resources = [_make_resource(user_id, str(i)) for i in range(n_resources)]
    db = _make_mock_db(resources)

    result = handle_search(user_id, {"technology": "AWS"}, db)
    assert result["statusCode"] == 200
    items = json.loads(result["body"])

    all_ids = {r["resourceId"] for r in resources}
    for item in items:
        assert item["resourceId"] in all_ids, (
            f"Result contains resourceId not in user's resource set: {item['resourceId']}"
        )


# ===========================================================================
# Property 23: Search with unrecognized filter key returns HTTP 400
#
# Feature: learningpath-ai, Property 23: Search with unrecognized filter key returns HTTP 400
# ===========================================================================


@given(
    user_id=_user_id,
    bad_key=st.text(min_size=1, max_size=30).filter(
        lambda k: k not in SUPPORTED_FILTER_KEYS and k.strip()
    ),
    value=_simple_text,
)
@settings(max_examples=100)
def test_property23_unrecognized_filter_key_returns_400(user_id, bad_key, value):
    """
    # Feature: learningpath-ai, Property 23: Search with unrecognized filter key returns HTTP 400

    Any search request containing a key not in the supported set must return HTTP 400.

    Validates: Requirements 8.6
    """
    db = _make_mock_db([])
    result = handle_search(user_id, {bad_key: value}, db)

    assert result["statusCode"] == 400, (
        f"Expected 400 for unrecognized filter key '{bad_key}', got {result['statusCode']}"
    )
    body = json.loads(result["body"])
    assert body["error"] == "VALIDATION_ERROR"


@given(
    user_id=_user_id,
    valid_key=st.sampled_from(sorted(SUPPORTED_FILTER_KEYS)),
    bad_key=st.text(min_size=1, max_size=30).filter(
        lambda k: k not in SUPPORTED_FILTER_KEYS and k.strip()
    ),
    value=_simple_text,
)
@settings(max_examples=100)
def test_property23_mixed_valid_and_invalid_keys_returns_400(
    user_id, valid_key, bad_key, value
):
    """
    # Feature: learningpath-ai, Property 23: Search with unrecognized filter key returns HTTP 400

    When valid and invalid keys are mixed together, the response must still be HTTP 400.

    Validates: Requirements 8.6
    """
    db = _make_mock_db([])
    result = handle_search(user_id, {valid_key: value, bad_key: value}, db)

    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body["error"] == "VALIDATION_ERROR"
    # Error message should mention the unrecognized key
    assert bad_key in body["message"]


@given(
    user_id=_user_id,
    valid_key=st.sampled_from(sorted(SUPPORTED_FILTER_KEYS)),
    value=_simple_text,
)
@settings(max_examples=100)
def test_property23_valid_keys_never_return_400_for_key_validation(
    user_id, valid_key, value
):
    """
    # Feature: learningpath-ai, Property 23: Search with unrecognized filter key returns HTTP 400

    Recognized filter keys must never trigger the unrecognized-key 400 response.
    (The response may be 200 with an empty or non-empty list.)

    Validates: Requirements 8.6 (negative — supported keys are accepted)
    """
    db = _make_mock_db([])
    result = handle_search(user_id, {valid_key: value}, db)

    # Should not be a 400 triggered by key validation
    if result["statusCode"] == 400:
        body = json.loads(result["body"])
        assert "Unrecognized filter key" not in body.get("message", ""), (
            f"Recognized key '{valid_key}' must not produce an unrecognized-key 400"
        )
