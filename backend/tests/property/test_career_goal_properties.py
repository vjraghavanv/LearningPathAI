"""
Property-based tests for CareerGoalManager Lambda (Properties 10, 11).

# Feature: learningpath-ai, Property 10: Career goal profile persistence round-trip
# Feature: learningpath-ai, Property 11: Career goal field validation

Validates: Requirements 3.1–3.7
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.career_goal_manager.handler import (
    MAX_CAREER_GOAL_LENGTH,
    MAX_WEEKLY_HOURS,
    MIN_WEEKLY_HOURS,
    VALID_PACES,
    VALID_SKILL_LEVELS,
    _handle_post,
    validate_career_goal_profile,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_career_goal = st.text(min_size=1, max_size=MAX_CAREER_GOAL_LENGTH)
valid_skill_level = st.sampled_from(sorted(VALID_SKILL_LEVELS))
valid_weekly_hours = st.integers(min_value=MIN_WEEKLY_HOURS, max_value=MAX_WEEKLY_HOURS)
valid_pace = st.sampled_from(sorted(VALID_PACES))
user_id_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
))


def valid_profile_strategy():
    return st.fixed_dictionaries(
        {
            "careerGoal": valid_career_goal,
            "currentSkillLevel": valid_skill_level,
            "weeklyStudyHours": valid_weekly_hours,
        },
        optional={
            "preferredLearningPace": valid_pace,
            "targetCompletionDate": st.just("2025-12-31"),
        },
    )


def _make_db():
    db = MagicMock()
    store = {}

    def put_item(Item):
        store[(Item["userId"], Item["resourceId"])] = dict(Item)
        return {}

    def get_item(Key):
        item = store.get((Key["userId"], Key["resourceId"]))
        return {"Item": dict(item)} if item else {}

    db.put_item.side_effect = put_item
    db.get_item.side_effect = get_item
    db._store = store
    return db


# ---------------------------------------------------------------------------
# Property 10: Career goal profile persistence round-trip
# ---------------------------------------------------------------------------

@given(profile=valid_profile_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property10_profile_persistence_round_trip(profile, user_id):
    """
    # Feature: learningpath-ai, Property 10: Career goal profile persistence round-trip

    For any valid career goal profile, persisting it and then retrieving it
    should return a record with all the submitted field values.

    Validates: Requirements 3.1, 3.2
    """
    db = _make_db()
    result = _handle_post(user_id, profile, db)
    assert result["statusCode"] == 201

    saved = db._store.get((user_id, "PROFILE#career_goal"))
    assert saved is not None, "Profile must be persisted to DynamoDB"

    assert saved["careerGoal"] == profile["careerGoal"]
    assert saved["currentSkillLevel"] == profile["currentSkillLevel"]
    assert saved["weeklyStudyHours"] == int(profile["weeklyStudyHours"])
    assert saved["userId"] == user_id


@given(profile=valid_profile_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property10_response_reflects_submitted_fields(profile, user_id):
    """
    # Feature: learningpath-ai, Property 10: Career goal profile persistence round-trip

    The 201 response body must contain all the submitted field values.

    Validates: Requirements 3.1, 3.2
    """
    db = _make_db()
    result = _handle_post(user_id, profile, db)
    assert result["statusCode"] == 201

    data = json.loads(result["body"])
    assert data["careerGoal"] == profile["careerGoal"]
    assert data["currentSkillLevel"] == profile["currentSkillLevel"]
    assert data["weeklyStudyHours"] == int(profile["weeklyStudyHours"])


# ---------------------------------------------------------------------------
# Property 11: Career goal field validation
# ---------------------------------------------------------------------------

@given(
    career_goal=st.text(min_size=MAX_CAREER_GOAL_LENGTH + 1, max_size=MAX_CAREER_GOAL_LENGTH + 50),
    skill_level=valid_skill_level,
    hours=valid_weekly_hours,
)
@settings(max_examples=100)
def test_property11_career_goal_too_long_returns_400(career_goal, skill_level, hours):
    """
    # Feature: learningpath-ai, Property 11: Career goal field validation

    Any career goal string longer than 200 characters must be rejected with HTTP 400.

    Validates: Requirements 3.3, 3.7
    """
    body = {"careerGoal": career_goal, "currentSkillLevel": skill_level, "weeklyStudyHours": hours}
    result = validate_career_goal_profile(body)
    assert result is not None
    assert result["statusCode"] == 400


@given(
    career_goal=valid_career_goal,
    invalid_skill=st.text(min_size=1, max_size=20).filter(lambda s: s not in VALID_SKILL_LEVELS),
    hours=valid_weekly_hours,
)
@settings(max_examples=100)
def test_property11_invalid_skill_level_returns_400(career_goal, invalid_skill, hours):
    """
    # Feature: learningpath-ai, Property 11: Career goal field validation

    Any currentSkillLevel not in {Beginner, Intermediate, Advanced} must be rejected.

    Validates: Requirements 3.4, 3.7
    """
    body = {"careerGoal": career_goal, "currentSkillLevel": invalid_skill, "weeklyStudyHours": hours}
    result = validate_career_goal_profile(body)
    assert result is not None
    assert result["statusCode"] == 400


@given(
    career_goal=valid_career_goal,
    skill_level=valid_skill_level,
    hours=st.integers().filter(lambda h: not (MIN_WEEKLY_HOURS <= h <= MAX_WEEKLY_HOURS)),
)
@settings(max_examples=100)
def test_property11_weekly_hours_out_of_range_returns_400(career_goal, skill_level, hours):
    """
    # Feature: learningpath-ai, Property 11: Career goal field validation

    Any weeklyStudyHours outside [1, 168] must be rejected with HTTP 400.

    Validates: Requirements 3.5, 3.7
    """
    body = {"careerGoal": career_goal, "currentSkillLevel": skill_level, "weeklyStudyHours": hours}
    result = validate_career_goal_profile(body)
    assert result is not None
    assert result["statusCode"] == 400


@given(
    career_goal=valid_career_goal,
    skill_level=valid_skill_level,
    hours=valid_weekly_hours,
    invalid_pace=st.text(min_size=1, max_size=20).filter(lambda s: s not in VALID_PACES),
)
@settings(max_examples=100)
def test_property11_invalid_pace_returns_400(career_goal, skill_level, hours, invalid_pace):
    """
    # Feature: learningpath-ai, Property 11: Career goal field validation

    Any preferredLearningPace not in {Slow, Moderate, Fast} must be rejected.

    Validates: Requirements 3.6, 3.7
    """
    body = {
        "careerGoal": career_goal,
        "currentSkillLevel": skill_level,
        "weeklyStudyHours": hours,
        "preferredLearningPace": invalid_pace,
    }
    result = validate_career_goal_profile(body)
    assert result is not None
    assert result["statusCode"] == 400


@given(profile=valid_profile_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property11_valid_profile_passes_all_validation(profile, user_id):
    """
    # Feature: learningpath-ai, Property 11: Career goal field validation

    Any profile with all valid fields must pass validation (no 400 error).

    Validates: Requirements 3.3–3.7 (positive case)
    """
    result = validate_career_goal_profile(profile)
    assert result is None, f"Valid profile failed validation: {result}"
