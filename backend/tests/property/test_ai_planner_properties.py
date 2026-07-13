"""
Property-based tests for AI_Planner Lambda (Properties 12, 13, 14, 21) and
Pretty_Printer Learning_Plan serialization (Property 15).

# Feature: learningpath-ai, Property 12: Learning_Plan structural invariants
# Feature: learningpath-ai, Property 13: Learning_Plan respects daily study budget
# Feature: learningpath-ai, Property 14: Completed and Skipped resources excluded from plans
# Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip
# Feature: learningpath-ai, Property 21: Plan preserved on regeneration failure

Validates: Requirements 4.3, 4.5, 4.6, 4.7, 4.10, 7.1, 7.3, 7.5
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.ai_planner.handler import (
    build_learning_plan,
    _parse_duration_hours,
    fetch_active_resources,
    invoke_bedrock_planner,
    EXCLUDED_STATUSES,
    handler,
)
from shared.pretty_printer import (
    DAILY_SCHEDULE_KEYS,
    LEARNING_PLAN_KEYS,
    serialize_learning_plan,
)

# ---------------------------------------------------------------------------
# Strategies for generating Learning_Plan data
# ---------------------------------------------------------------------------

# Strategy for day field (positive integer)
day_strategy = st.integers(min_value=1, max_value=365)

# Strategy for string fields in daily schedule
schedule_string_strategy = st.text(min_size=0, max_size=200)

# Strategy for ISO date strings (DynamoDB-only field that should be excluded)
date_strategy = st.dates().map(lambda d: d.isoformat())

# Strategy for a single daily schedule entry (as stored in DynamoDB)
def daily_schedule_entry_strategy():
    """Generate a DynamoDB daily schedule entry including the 'date' field."""
    return st.fixed_dictionaries(
        {
            "day": day_strategy,
            "date": date_strategy,        # DynamoDB-only field — must be excluded
            "resourceId": schedule_string_strategy,
            "estimatedDuration": schedule_string_strategy,
            "recommendationReason": schedule_string_strategy,
        }
    )


# Strategy for string list fields (weeklyRoadmap, recommendedProjects, etc.)
string_list_strategy = st.lists(
    st.text(min_size=0, max_size=100),
    min_size=0,
    max_size=10,
)

# Strategy for a complete Learning_Plan DynamoDB record
def learning_plan_strategy():
    """Generate arbitrary valid Learning_Plan dicts as stored in DynamoDB."""
    return st.fixed_dictionaries(
        {
            # DynamoDB-only identity fields (should be excluded from output)
            "userId": st.text(min_size=1, max_size=50),
            "resourceId": st.just("PLAN#active"),
            "generatedAt": st.datetimes().map(lambda dt: dt.isoformat()),
            "careerGoalSnapshot": st.dictionaries(
                st.text(min_size=1, max_size=20),
                st.text(min_size=0, max_size=50),
                max_size=5,
            ),
            # Bedrock prompt fields (should be included in output)
            "dailySchedule": st.lists(
                daily_schedule_entry_strategy(),
                min_size=0,
                max_size=10,
            ),
            "weeklyRoadmap": string_list_strategy,
            "recommendedProjects": string_list_strategy,
            "certificationRecommendations": string_list_strategy,
            "estimatedCompletionTimeline": schedule_string_strategy,
        }
    )


# ---------------------------------------------------------------------------
# Strategies for Property 12
# ---------------------------------------------------------------------------

_user_id_strategy = st.text(
    min_size=1, max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
)

_schedule_entry_strategy = st.fixed_dictionaries({
    "day": st.integers(min_value=1, max_value=365),
    "resourceId": st.text(min_size=1, max_size=50),
    "estimatedDuration": st.sampled_from(["0.5 hours", "1 hour", "1.5 hours", "2 hours"]),
    "recommendationReason": st.text(min_size=1, max_size=100),
})


def _raw_plan_strategy(min_days: int = 7):
    return st.fixed_dictionaries({
        "dailySchedule": st.lists(_schedule_entry_strategy, min_size=min_days, max_size=14),
        "weeklyRoadmap": st.lists(st.text(max_size=50), max_size=5),
        "recommendedProjects": st.lists(st.text(max_size=50), max_size=5),
        "certificationRecommendations": st.lists(st.text(max_size=50), max_size=5),
        "estimatedCompletionTimeline": st.text(max_size=50),
        "resourcePriorityScores": st.dictionaries(
            st.text(min_size=1, max_size=30),
            st.integers(min_value=0, max_value=100),
            max_size=10,
        ),
    })


def _profile_strategy():
    return st.fixed_dictionaries({
        "careerGoal": st.text(min_size=1, max_size=100),
        "currentSkillLevel": st.sampled_from(["Beginner", "Intermediate", "Advanced"]),
        "weeklyStudyHours": st.integers(min_value=1, max_value=168),
        "preferredLearningPace": st.sampled_from(["Slow", "Moderate", "Fast"]),
    })


# ---------------------------------------------------------------------------
# Property 12: Learning_Plan structural invariants
#
# Feature: learningpath-ai, Property 12: Learning_Plan structural invariants
# ---------------------------------------------------------------------------


@given(raw_plan=_raw_plan_strategy(min_days=7), profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property12_daily_schedule_has_at_least_7_days(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    For any generated Learning_Plan, the daily schedule must contain at least 7 entries.

    Validates: Requirements 4.3
    """
    plan = build_learning_plan(user_id, raw_plan, profile, [])
    assert len(plan["dailySchedule"]) >= 7, (
        f"Expected ≥7 days in dailySchedule, got {len(plan['dailySchedule'])}"
    )


@given(raw_plan=_raw_plan_strategy(min_days=7), profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property12_each_schedule_entry_has_required_fields(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    Each daily schedule entry must include resourceId, estimatedDuration,
    and recommendationReason.

    Validates: Requirements 4.3
    """
    plan = build_learning_plan(user_id, raw_plan, profile, [])
    required = ("resourceId", "estimatedDuration", "recommendationReason")
    for i, entry in enumerate(plan["dailySchedule"]):
        for field in required:
            assert field in entry, (
                f"dailySchedule[{i}] is missing required field '{field}': {entry}"
            )


@given(raw_plan=_raw_plan_strategy(min_days=7), profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property12_schedule_entries_have_string_fields(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    The resourceId, estimatedDuration, and recommendationReason fields in each
    daily schedule entry must be str instances.

    Validates: Requirements 4.3
    """
    plan = build_learning_plan(user_id, raw_plan, profile, [])
    string_fields = ("resourceId", "estimatedDuration", "recommendationReason")
    for i, entry in enumerate(plan["dailySchedule"]):
        for field in string_fields:
            assert isinstance(entry[field], str), (
                f"dailySchedule[{i}]['{field}'] must be str, "
                f"got {type(entry[field])!r}: {entry[field]!r}"
            )


@given(raw_plan=_raw_plan_strategy(min_days=7), profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property12_schedule_entry_day_is_positive_integer(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    The 'day' field in each daily schedule entry must be a positive integer.

    Validates: Requirements 4.3
    """
    plan = build_learning_plan(user_id, raw_plan, profile, [])
    for i, entry in enumerate(plan["dailySchedule"]):
        assert isinstance(entry["day"], int), (
            f"dailySchedule[{i}]['day'] must be int, got {type(entry['day'])}"
        )
        assert entry["day"] >= 1, (
            f"dailySchedule[{i}]['day'] must be ≥ 1, got {entry['day']}"
        )


@given(
    raw_plan=_raw_plan_strategy(min_days=7),
    profile=_profile_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property12_all_priority_scores_in_valid_range(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    All Priority_Score values assigned to resources must be in [0, 100].

    Validates: Requirements 4.6
    """
    # Feed the raw plan's resource IDs in as active resources so they appear
    # in the priority score output.
    resources = [
        {"resourceId": rid, "learningStatus": "Not Started"}
        for rid in raw_plan.get("resourcePriorityScores", {}).keys()
    ]
    plan = build_learning_plan(user_id, raw_plan, profile, resources)
    for rid, score in plan["resourcePriorityScores"].items():
        assert 0 <= score <= 100, (
            f"Priority score {score} for resource '{rid}' is outside [0, 100]"
        )


@given(
    raw_plan=_raw_plan_strategy(min_days=0),  # may start with fewer than 7 days
    profile=_profile_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property12_sparse_input_still_produces_7_days(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    Even when Bedrock returns a dailySchedule with fewer than 7 entries,
    build_learning_plan must pad the schedule to reach at least 7 days.

    Validates: Requirements 4.3
    """
    # Truncate to fewer than 7 days to test padding
    raw_plan["dailySchedule"] = raw_plan["dailySchedule"][:3]
    plan = build_learning_plan(user_id, raw_plan, profile, [])
    assert len(plan["dailySchedule"]) >= 7, (
        f"Expected padding to ≥7 days, got {len(plan['dailySchedule'])}"
    )


@given(raw_plan=_raw_plan_strategy(min_days=7), profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property12_plan_contains_required_top_level_fields(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 12: Learning_Plan structural invariants

    The generated plan must contain all top-level fields required by the
    Learning_Plan schema: dailySchedule, weeklyRoadmap, recommendedProjects,
    certificationRecommendations, estimatedCompletionTimeline,
    resourcePriorityScores.

    Validates: Requirements 4.3, 4.4
    """
    plan = build_learning_plan(user_id, raw_plan, profile, [])
    required_fields = (
        "dailySchedule",
        "weeklyRoadmap",
        "recommendedProjects",
        "certificationRecommendations",
        "estimatedCompletionTimeline",
        "resourcePriorityScores",
    )
    for field in required_fields:
        assert field in plan, (
            f"Generated plan is missing required top-level field '{field}': {list(plan.keys())}"
        )


# ---------------------------------------------------------------------------
# Property 13: Learning_Plan respects daily study budget
#
# Feature: learningpath-ai, Property 13: Learning_Plan respects daily study budget
# ---------------------------------------------------------------------------


@given(raw_plan=_raw_plan_strategy(min_days=7), profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property13_no_day_exceeds_daily_budget(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 13: Learning_Plan respects daily study budget

    For any generated Learning_Plan and the user profile used to create it,
    no single day's total scheduled study time should exceed the user's average
    daily availability (weeklyStudyHours / 7).

    Validates: Requirements 4.5
    """
    weekly_hours = profile["weeklyStudyHours"]
    daily_budget = weekly_hours / 7

    plan = build_learning_plan(user_id, raw_plan, profile, [])

    for i, entry in enumerate(plan["dailySchedule"]):
        duration_h = _parse_duration_hours(str(entry.get("estimatedDuration", "0")))
        # Allow a small tolerance for floating-point string round-trip
        # (e.g. budget 0.286h stored as "0.3 hours" re-parses as 0.3h)
        assert duration_h <= daily_budget + 0.1, (
            f"Day {i + 1}: duration {duration_h:.3f}h exceeds daily budget "
            f"{daily_budget:.3f}h (weeklyStudyHours={weekly_hours})"
        )


@given(
    weekly_hours=st.integers(min_value=1, max_value=168),
    duration_str=st.sampled_from(["3 hours", "4 hours", "6 hours", "8 hours", "12 hours"]),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property13_over_budget_entry_is_clamped(weekly_hours, duration_str, user_id):
    """
    # Feature: learningpath-ai, Property 13: Learning_Plan respects daily study budget

    When a raw Bedrock schedule entry exceeds the daily budget, build_learning_plan
    must clamp the entry's estimatedDuration to the daily budget, not reject it.

    Validates: Requirements 4.5
    """
    daily_budget = weekly_hours / 7
    profile = {
        "careerGoal": "Become AWS Cloud Engineer",
        "currentSkillLevel": "Intermediate",
        "weeklyStudyHours": weekly_hours,
        "preferredLearningPace": "Moderate",
    }
    raw_plan = {
        "dailySchedule": [
            {
                "day": d,
                "resourceId": f"RESOURCE#r{d}",
                "estimatedDuration": duration_str,
                "recommendationReason": "test",
            }
            for d in range(1, 8)
        ],
        "weeklyRoadmap": [],
        "recommendedProjects": [],
        "certificationRecommendations": [],
        "estimatedCompletionTimeline": "3 months",
        "resourcePriorityScores": {},
    }

    plan = build_learning_plan(user_id, raw_plan, profile, [])

    for i, entry in enumerate(plan["dailySchedule"]):
        duration_h = _parse_duration_hours(str(entry.get("estimatedDuration", "0")))
        # Allow a small tolerance for floating-point string round-trip
        # (e.g. budget 0.286h stored as "0.3 hours" re-parses as 0.3h)
        assert duration_h <= daily_budget + 0.1, (
            f"Day {i + 1}: clamped duration {duration_h:.3f}h still exceeds "
            f"daily budget {daily_budget:.3f}h"
        )


@given(
    weekly_hours=st.integers(min_value=1, max_value=168),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property13_zero_hour_entries_always_within_budget(weekly_hours, user_id):
    """
    # Feature: learningpath-ai, Property 13: Learning_Plan respects daily study budget

    Rest/review day entries with '0 hours' must always be within any daily budget.

    Validates: Requirements 4.5
    """
    daily_budget = weekly_hours / 7
    profile = {
        "careerGoal": "Become DevOps Engineer",
        "currentSkillLevel": "Beginner",
        "weeklyStudyHours": weekly_hours,
        "preferredLearningPace": "Slow",
    }
    raw_plan = {
        "dailySchedule": [],  # empty — will be padded with rest days
        "weeklyRoadmap": [],
        "recommendedProjects": [],
        "certificationRecommendations": [],
        "estimatedCompletionTimeline": "6 months",
        "resourcePriorityScores": {},
    }

    plan = build_learning_plan(user_id, raw_plan, profile, [])

    for i, entry in enumerate(plan["dailySchedule"]):
        duration_h = _parse_duration_hours(str(entry.get("estimatedDuration", "0")))
        assert duration_h <= daily_budget + 1e-9, (
            f"Padded rest day {i + 1} has duration {duration_h:.3f}h "
            f"exceeding budget {daily_budget:.3f}h"
        )


def _resource_strategy(learning_status=None):
    base = st.fixed_dictionaries({
        "userId": _user_id_strategy,
        "resourceId": st.text(min_size=1, max_size=50).map(lambda s: f"RESOURCE#{s}"),
        "title": st.text(min_size=1, max_size=80),
        "resourceType": st.sampled_from(["Technical Article", "Online Course", "PDF"]),
        "technology": st.text(max_size=30),
    })
    if learning_status:
        return base.map(lambda r: {**r, "learningStatus": learning_status})
    return base.flatmap(
        lambda r: st.sampled_from(["Not Started", "In Progress", "Completed", "Skipped"])
        .map(lambda s: {**r, "learningStatus": s})
    )


# ---------------------------------------------------------------------------
# Property 14: Completed and Skipped resources excluded from plans
#
# Feature: learningpath-ai, Property 14: Completed and Skipped resources excluded from plans
# ---------------------------------------------------------------------------


@given(
    completed=st.lists(_resource_strategy("Completed"), min_size=1, max_size=5),
    skipped=st.lists(_resource_strategy("Skipped"), min_size=0, max_size=3),
    active=st.lists(_resource_strategy("Not Started"), min_size=0, max_size=5),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property14_fetch_active_resources_excludes_completed_and_skipped(
    completed, skipped, active, user_id
):
    """
    # Feature: learningpath-ai, Property 14: Completed and Skipped resources excluded from plans

    fetch_active_resources must never return resources with Learning_Status
    Completed or Skipped, regardless of how many such resources exist in DynamoDB.

    Validates: Requirements 4.7, 7.1, 7.3
    """
    # Ensure no resourceId collision across the three lists so the assertion is unambiguous
    all_ids = (
        [r["resourceId"] for r in completed]
        + [r["resourceId"] for r in skipped]
        + [r["resourceId"] for r in active]
    )
    assume(len(all_ids) == len(set(all_ids)))

    db = MagicMock()
    db.query.return_value = {"Items": completed + skipped + active}

    result = fetch_active_resources(user_id, db)

    excluded_ids = {r["resourceId"] for r in completed + skipped}
    returned_ids = {r["resourceId"] for r in result}
    overlap = excluded_ids & returned_ids
    assert not overlap, (
        f"Completed/Skipped resource IDs found in active list: {overlap}"
    )


@given(
    in_progress=st.lists(_resource_strategy("In Progress"), min_size=0, max_size=5),
    not_started=st.lists(_resource_strategy("Not Started"), min_size=0, max_size=5),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property14_fetch_active_resources_includes_in_progress_and_not_started(
    in_progress, not_started, user_id
):
    """
    # Feature: learningpath-ai, Property 14: Completed and Skipped resources excluded from plans

    fetch_active_resources must return all resources with Learning_Status
    'Not Started' or 'In Progress'.

    Validates: Requirements 4.7
    """
    db = MagicMock()
    db.query.return_value = {"Items": in_progress + not_started}

    result = fetch_active_resources(user_id, db)

    expected_ids = {r["resourceId"] for r in in_progress + not_started}
    returned_ids = {r["resourceId"] for r in result}
    assert returned_ids == expected_ids, (
        f"Expected active IDs {expected_ids}, got {returned_ids}"
    )


@given(
    completed_ids=st.lists(
        st.text(min_size=1, max_size=30).map(lambda s: f"RESOURCE#{s}"),
        min_size=1, max_size=5, unique=True,
    ),
    profile=_profile_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property14_completed_ids_absent_from_priority_scores(
    completed_ids, profile, user_id
):
    """
    # Feature: learningpath-ai, Property 14: Completed and Skipped resources excluded from plans

    When active_resources does not include completed/skipped IDs, those IDs
    must not appear in the plan's resourcePriorityScores.

    Validates: Requirements 4.7, 7.3
    """
    # raw_plan references only completed IDs in priorityScores
    raw_plan = {
        "dailySchedule": [],
        "weeklyRoadmap": [],
        "recommendedProjects": [],
        "certificationRecommendations": [],
        "estimatedCompletionTimeline": "3 months",
        "resourcePriorityScores": {rid: 80 for rid in completed_ids},
    }
    # active_resources list contains none of the completed IDs
    active_resources = []

    plan = build_learning_plan(user_id, raw_plan, profile, active_resources)

    completed_id_set = set(completed_ids)
    for rid in plan["resourcePriorityScores"].keys():
        assert rid not in completed_id_set, (
            f"Completed resource '{rid}' appeared in plan's resourcePriorityScores"
        )


@given(
    excluded_status=st.sampled_from(list(EXCLUDED_STATUSES)),
    resources=st.lists(
        st.fixed_dictionaries({
            "userId": _user_id_strategy,
            "resourceId": st.text(min_size=1, max_size=40).map(lambda s: f"RESOURCE#{s}"),
            "learningStatus": st.just("Not Started"),
        }),
        min_size=0, max_size=5,
    ),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property14_excluded_statuses_constant_covers_completed_and_skipped(
    excluded_status, resources, user_id
):
    """
    # Feature: learningpath-ai, Property 14: Completed and Skipped resources excluded from plans

    EXCLUDED_STATUSES must contain both 'Completed' and 'Skipped'.
    Any resource whose learningStatus is in EXCLUDED_STATUSES must not appear
    in the result of fetch_active_resources.

    Validates: Requirements 4.7
    """
    assert "Completed" in EXCLUDED_STATUSES
    assert "Skipped" in EXCLUDED_STATUSES

    excluded_resource = {
        "userId": user_id,
        "resourceId": "RESOURCE#excluded",
        "learningStatus": excluded_status,
    }
    db = MagicMock()
    db.query.return_value = {"Items": resources + [excluded_resource]}

    result = fetch_active_resources(user_id, db)
    returned_ids = {r["resourceId"] for r in result}
    assert "RESOURCE#excluded" not in returned_ids, (
        f"Resource with status '{excluded_status}' must not appear in active list"
    )


# ---------------------------------------------------------------------------
# Property 21: Plan preserved on regeneration failure
#
# Feature: learningpath-ai, Property 21: Plan preserved on regeneration failure
# ---------------------------------------------------------------------------


@given(
    raw_plan=_raw_plan_strategy(min_days=7),
    profile=_profile_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property21_invoke_bedrock_returns_none_on_exception(raw_plan, profile, user_id):
    """
    # Feature: learningpath-ai, Property 21: Plan preserved on regeneration failure

    When Bedrock raises any exception, invoke_bedrock_planner must return None
    so the caller knows not to persist a new plan.

    Validates: Requirements 7.5
    """
    failing_client = MagicMock()
    failing_client.invoke_model.side_effect = Exception("Bedrock unavailable")
    result = invoke_bedrock_planner("test prompt", bedrock_client=failing_client)
    assert result is None, (
        "invoke_bedrock_planner must return None on Bedrock exception"
    )


@given(profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property21_handler_returns_503_on_bedrock_failure(profile, user_id):
    """
    # Feature: learningpath-ai, Property 21: Plan preserved on regeneration failure

    When Bedrock fails during plan generation, the handler must return HTTP 503
    and must NOT call db.put_item, leaving the last valid plan intact.

    Validates: Requirements 7.5
    """
    event = {
        "httpMethod": "POST",
        "path": "/learning-plan",
        "requestContext": {
            "requestId": "req-test",
            "authorizer": {"claims": {"sub": user_id}},
        },
        "body": "{}",
    }

    with patch("lambdas.ai_planner.handler.DynamoDBClient") as MockDB, \
         patch("lambdas.ai_planner.handler.boto3") as mock_boto3:
        db = MagicMock()
        db.get_item.return_value = {
            "Item": {**profile, "userId": user_id, "resourceId": "PROFILE#career_goal"}
        }
        db.query.return_value = {"Items": []}
        MockDB.return_value = db

        bedrock_client = MagicMock()
        bedrock_client.invoke_model.side_effect = Exception("Bedrock down")
        mock_boto3.client.return_value = bedrock_client

        result = handler(event, None)

    assert result["statusCode"] == 503, (
        f"Expected 503 on Bedrock failure, got {result['statusCode']}"
    )
    db.put_item.assert_not_called()


@given(profile=_profile_strategy(), user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property21_503_body_contains_error_key(profile, user_id):
    """
    # Feature: learningpath-ai, Property 21: Plan preserved on regeneration failure

    The 503 response body on Bedrock failure must contain an 'error' key so
    the frontend can display a meaningful message rather than crash.

    Validates: Requirements 7.5, 4.8
    """
    event = {
        "httpMethod": "POST",
        "path": "/learning-plan",
        "requestContext": {
            "requestId": "req-test",
            "authorizer": {"claims": {"sub": user_id}},
        },
        "body": "{}",
    }

    with patch("lambdas.ai_planner.handler.DynamoDBClient") as MockDB, \
         patch("lambdas.ai_planner.handler.boto3") as mock_boto3:
        db = MagicMock()
        db.get_item.return_value = {
            "Item": {**profile, "userId": user_id, "resourceId": "PROFILE#career_goal"}
        }
        db.query.return_value = {"Items": []}
        MockDB.return_value = db
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.side_effect = Exception("Bedrock down")
        mock_boto3.client.return_value = bedrock_client

        result = handler(event, None)

    body = json.loads(result["body"])
    assert "error" in body, (
        f"503 response body must contain 'error' key, got keys: {list(body.keys())}"
    )


# ---------------------------------------------------------------------------
# Property 15: Learning_Plan serialization round-trip
#
# Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip
# ---------------------------------------------------------------------------


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_output_contains_exactly_learning_plan_keys(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan DynamoDB record, serialize_learning_plan must return
    a dict containing exactly the keys defined in LEARNING_PLAN_KEYS.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    assert set(result.keys()) == set(LEARNING_PLAN_KEYS), (
        f"Output keys {set(result.keys())} do not match required Bedrock keys "
        f"{set(LEARNING_PLAN_KEYS)}"
    )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_daily_schedule_entries_have_exactly_daily_schedule_keys(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan, each entry in the serialized dailySchedule must
    contain exactly the keys defined in DAILY_SCHEDULE_KEYS — no more, no less.
    In particular, the DynamoDB-only 'date' key must not be present.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    for i, entry in enumerate(result["dailySchedule"]):
        assert set(entry.keys()) == set(DAILY_SCHEDULE_KEYS), (
            f"dailySchedule[{i}] keys {set(entry.keys())} do not match "
            f"required keys {set(DAILY_SCHEDULE_KEYS)}"
        )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_date_field_excluded_from_daily_schedule(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan whose dailySchedule entries contain a 'date' field
    (as stored in DynamoDB), that field must NOT appear in the serialized output.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    for i, entry in enumerate(result["dailySchedule"]):
        assert "date" not in entry, (
            f"dailySchedule[{i}] should not contain 'date' key, "
            f"but got keys: {set(entry.keys())}"
        )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_all_string_fields_in_daily_schedule_are_strings(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan, all string fields in each serialized dailySchedule
    entry (resourceId, estimatedDuration, recommendationReason) must be actual
    Python str instances.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    string_keys = ("resourceId", "estimatedDuration", "recommendationReason")
    for i, entry in enumerate(result["dailySchedule"]):
        for field in string_keys:
            assert isinstance(entry[field], str), (
                f"dailySchedule[{i}]['{field}'] must be str, "
                f"got {type(entry[field])}: {entry[field]!r}"
            )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_list_fields_are_lists_of_strings(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan, the serialized weeklyRoadmap, recommendedProjects,
    and certificationRecommendations must each be lists of strings.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    list_fields = ("weeklyRoadmap", "recommendedProjects", "certificationRecommendations")
    for field in list_fields:
        value = result[field]
        assert isinstance(value, list), (
            f"'{field}' must be a list, got {type(value)}"
        )
        for j, item in enumerate(value):
            assert isinstance(item, str), (
                f"'{field}[{j}]' must be a str, got {type(item)}: {item!r}"
            )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_estimated_completion_timeline_is_string(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan, the serialized estimatedCompletionTimeline must be
    a string.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    assert isinstance(result["estimatedCompletionTimeline"], str), (
        f"estimatedCompletionTimeline must be str, "
        f"got {type(result['estimatedCompletionTimeline'])}"
    )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_json_round_trip(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan, json.dumps(serialize_learning_plan(plan)) must be
    parseable back to a JSON object structurally equivalent to the serialized
    output.

    Validates: Requirements 4.10
    """
    result = serialize_learning_plan(learning_plan)
    serialized = json.dumps(result)
    parsed = json.loads(serialized)
    assert parsed == result, (
        f"Round-trip failed: json.loads(json.dumps(result)) != result"
    )


@given(learning_plan=learning_plan_strategy())
@settings(max_examples=100)
def test_property15_dynamodb_only_fields_excluded(learning_plan):
    """
    # Feature: learningpath-ai, Property 15: Learning_Plan serialization round-trip

    For any Learning_Plan DynamoDB record, the serialized output must NOT
    contain DynamoDB-only fields: userId, resourceId, generatedAt,
    careerGoalSnapshot.

    Validates: Requirements 4.10
    """
    dynamodb_only_keys = {"userId", "resourceId", "generatedAt", "careerGoalSnapshot"}
    result = serialize_learning_plan(learning_plan)
    for key in dynamodb_only_keys:
        assert key not in result, (
            f"DynamoDB-only key '{key}' should not appear in serialized output, "
            f"but got keys: {set(result.keys())}"
        )
