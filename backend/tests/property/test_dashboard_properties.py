"""
Property-based tests for DashboardAPI Lambda (Properties 16, 17, 18).

# Feature: learningpath-ai, Property 16: Dashboard response completeness
# Feature: learningpath-ai, Property 17: Completion percentage arithmetic
# Feature: learningpath-ai, Property 18: Study streak computation

Validates: Requirements 5.1, 5.3, 5.4
"""

import os
import sys

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.dashboard_api.handler import (
    build_dashboard_response,
    compute_completion_percentage,
    compute_study_streak,
    compute_todays_task,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_user_id_strategy = st.text(
    min_size=1, max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
)

_learning_status_strategy = st.sampled_from(
    ["Not Started", "In Progress", "Completed", "Skipped"]
)

def _resource_strategy(status=None):
    base = st.fixed_dictionaries({
        "userId": _user_id_strategy,
        "resourceId": st.text(min_size=1, max_size=40).map(lambda s: f"RESOURCE#{s}"),
        "title": st.text(min_size=1, max_size=80),
        "resourceType": st.sampled_from(["Technical Article", "Online Course", "PDF"]),
    })
    if status:
        return base.map(lambda r: {**r, "learningStatus": status})
    return base.flatmap(
        lambda r: _learning_status_strategy.map(lambda s: {**r, "learningStatus": s})
    )


def _daily_schedule_entry_strategy(today: str):
    return st.fixed_dictionaries({
        "day": st.integers(min_value=1, max_value=30),
        "date": st.just(today),
        "resourceId": st.text(min_size=1, max_size=40),
        "estimatedDuration": st.just("1 hour"),
        "recommendationReason": st.text(min_size=1, max_size=80),
    })


def _plan_strategy(today: str, min_days: int = 7):
    return st.fixed_dictionaries({
        "userId": _user_id_strategy,
        "resourceId": st.just("PLAN#active"),
        "dailySchedule": st.lists(
            _daily_schedule_entry_strategy(today),
            min_size=min_days, max_size=14,
        ),
        "weeklyRoadmap": st.lists(st.text(max_size=50), max_size=5),
        "recommendedProjects": st.lists(st.text(max_size=50), max_size=5),
        "certificationRecommendations": st.lists(st.text(max_size=50), max_size=5),
        "estimatedCompletionTimeline": st.text(max_size=50),
        "resourcePriorityScores": st.dictionaries(
            st.text(min_size=1, max_size=30),
            st.integers(min_value=0, max_value=100),
            max_size=5,
        ),
    })


def _streak_record_strategy():
    return st.fixed_dictionaries({
        "userId": _user_id_strategy,
        "resourceId": st.just("STREAK#current"),
        "currentStreak": st.integers(min_value=0, max_value=365),
        "lastCompletionDate": st.dates().map(lambda d: d.isoformat()),
    })


# ---------------------------------------------------------------------------
# Property 16: Dashboard response completeness
#
# Feature: learningpath-ai, Property 16: Dashboard response completeness
# ---------------------------------------------------------------------------

_REQUIRED_DASHBOARD_KEYS = (
    "userId",
    "todaysTask",
    "completionPercentage",
    "studyStreak",
    "weeklyProgress",
    "learningPlan",
    "priorityResources",
    "certificationRecommendations",
    "recommendedProjects",
    "weeklyRoadmap",
    "message",
)

_TODAY = "2026-07-12"  # fixed for deterministic today's-task tests


@given(
    plan=_plan_strategy(_TODAY),
    resources=st.lists(_resource_strategy(), min_size=1, max_size=10),
    streak=_streak_record_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property16_response_contains_all_required_keys(plan, resources, streak, user_id):
    """
    # Feature: learningpath-ai, Property 16: Dashboard response completeness

    For any user with an active Learning_Plan and at least one resource, the
    dashboard response must contain all required top-level keys.

    Validates: Requirements 5.1
    """
    response = build_dashboard_response(user_id, plan, resources, streak)
    for key in _REQUIRED_DASHBOARD_KEYS:
        assert key in response, (
            f"Dashboard response missing required key '{key}'. "
            f"Keys present: {list(response.keys())}"
        )


@given(
    plan=_plan_strategy(_TODAY),
    resources=st.lists(_resource_strategy(), min_size=1, max_size=10),
    streak=_streak_record_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property16_completion_percentage_is_float_in_valid_range(
    plan, resources, streak, user_id
):
    """
    # Feature: learningpath-ai, Property 16: Dashboard response completeness

    The completionPercentage field must always be a float in [0.0, 100.0].

    Validates: Requirements 5.1, 5.4
    """
    response = build_dashboard_response(user_id, plan, resources, streak)
    pct = response["completionPercentage"]
    assert isinstance(pct, float), f"completionPercentage must be float, got {type(pct)}"
    assert 0.0 <= pct <= 100.0, f"completionPercentage {pct} out of [0, 100]"


@given(
    plan=_plan_strategy(_TODAY),
    resources=st.lists(_resource_strategy(), min_size=1, max_size=10),
    streak=_streak_record_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property16_study_streak_is_non_negative_integer(
    plan, resources, streak, user_id
):
    """
    # Feature: learningpath-ai, Property 16: Dashboard response completeness

    The studyStreak field must always be a non-negative integer.

    Validates: Requirements 5.1, 5.3
    """
    response = build_dashboard_response(user_id, plan, resources, streak)
    s = response["studyStreak"]
    assert isinstance(s, int), f"studyStreak must be int, got {type(s)}"
    assert s >= 0, f"studyStreak must be ≥ 0, got {s}"


@given(
    plan=_plan_strategy(_TODAY),
    resources=st.lists(_resource_strategy(), min_size=1, max_size=10),
    streak=_streak_record_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property16_priority_resources_is_list(plan, resources, streak, user_id):
    """
    # Feature: learningpath-ai, Property 16: Dashboard response completeness

    The priorityResources field must always be a list.

    Validates: Requirements 5.1
    """
    response = build_dashboard_response(user_id, plan, resources, streak)
    assert isinstance(response["priorityResources"], list), (
        f"priorityResources must be a list, got {type(response['priorityResources'])}"
    )


@given(
    plan=_plan_strategy(_TODAY),
    resources=st.lists(_resource_strategy(), min_size=1, max_size=10),
    streak=_streak_record_strategy(),
    user_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property16_list_fields_are_lists(plan, resources, streak, user_id):
    """
    # Feature: learningpath-ai, Property 16: Dashboard response completeness

    weeklyRoadmap, certificationRecommendations, and recommendedProjects must
    all be lists.

    Validates: Requirements 5.1
    """
    response = build_dashboard_response(user_id, plan, resources, streak)
    for field in ("weeklyRoadmap", "certificationRecommendations", "recommendedProjects"):
        assert isinstance(response[field], list), (
            f"'{field}' must be a list, got {type(response[field])}"
        )


# ---------------------------------------------------------------------------
# Property 17: Completion percentage arithmetic
#
# Feature: learningpath-ai, Property 17: Completion percentage arithmetic
# ---------------------------------------------------------------------------


@given(
    completed_count=st.integers(min_value=0, max_value=20),
    in_progress_count=st.integers(min_value=0, max_value=10),
    not_started_count=st.integers(min_value=0, max_value=10),
    skipped_count=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=100)
def test_property17_completion_percentage_formula(
    completed_count, in_progress_count, not_started_count, skipped_count
):
    """
    # Feature: learningpath-ai, Property 17: Completion percentage arithmetic

    completionPercentage must equal
    (count Completed) / (count non-Skipped) * 100, rounded to 1 decimal.
    Returns 0.0 when there are no non-skipped resources.

    Validates: Requirements 5.4
    """
    resources = (
        [{"learningStatus": "Completed"}] * completed_count
        + [{"learningStatus": "In Progress"}] * in_progress_count
        + [{"learningStatus": "Not Started"}] * not_started_count
        + [{"learningStatus": "Skipped"}] * skipped_count
    )

    non_skipped = completed_count + in_progress_count + not_started_count
    if non_skipped == 0:
        expected = 0.0
    else:
        expected = round(completed_count / non_skipped * 100, 1)

    result = compute_completion_percentage(resources)
    assert result == expected, (
        f"Expected {expected}%, got {result}% "
        f"(completed={completed_count}, non_skipped={non_skipped})"
    )


@given(resources=st.lists(_resource_strategy(), min_size=0, max_size=20))
@settings(max_examples=100)
def test_property17_result_is_in_valid_range(resources):
    """
    # Feature: learningpath-ai, Property 17: Completion percentage arithmetic

    compute_completion_percentage must always return a value in [0.0, 100.0].

    Validates: Requirements 5.4
    """
    result = compute_completion_percentage(resources)
    assert 0.0 <= result <= 100.0, f"Percentage {result} is out of [0, 100]"


@given(resources=st.lists(_resource_strategy("Skipped"), min_size=1, max_size=10))
@settings(max_examples=100)
def test_property17_all_skipped_returns_zero(resources):
    """
    # Feature: learningpath-ai, Property 17: Completion percentage arithmetic

    When all resources are Skipped, the denominator is 0 and the result must be 0.0.

    Validates: Requirements 5.4
    """
    result = compute_completion_percentage(resources)
    assert result == 0.0, f"All-skipped resources should yield 0.0%, got {result}"


@given(resources=st.lists(_resource_strategy("Completed"), min_size=1, max_size=10))
@settings(max_examples=100)
def test_property17_all_completed_returns_100(resources):
    """
    # Feature: learningpath-ai, Property 17: Completion percentage arithmetic

    When all resources are Completed (none Skipped), the result must be 100.0.

    Validates: Requirements 5.4
    """
    result = compute_completion_percentage(resources)
    assert result == 100.0, f"All-completed resources should yield 100.0%, got {result}"


@given(resources=st.just([]))
@settings(max_examples=100)
def test_property17_empty_list_returns_zero(resources):
    """
    # Feature: learningpath-ai, Property 17: Completion percentage arithmetic

    An empty resource list must return 0.0.

    Validates: Requirements 5.4
    """
    result = compute_completion_percentage(resources)
    assert result == 0.0


# ---------------------------------------------------------------------------
# Property 18: Study streak computation
#
# Feature: learningpath-ai, Property 18: Study streak computation
# ---------------------------------------------------------------------------


@given(streak_record=_streak_record_strategy())
@settings(max_examples=100)
def test_property18_streak_matches_stored_value(streak_record):
    """
    # Feature: learningpath-ai, Property 18: Study streak computation

    compute_study_streak must return the exact integer stored in the
    streak record's currentStreak field.

    Validates: Requirements 5.3
    """
    result = compute_study_streak(streak_record)
    assert result == streak_record["currentStreak"], (
        f"Expected streak {streak_record['currentStreak']}, got {result}"
    )


@given(streak_record=st.none())
@settings(max_examples=100)
def test_property18_missing_streak_record_returns_zero(streak_record):
    """
    # Feature: learningpath-ai, Property 18: Study streak computation

    When no streak record exists in DynamoDB, compute_study_streak must return 0.

    Validates: Requirements 5.3
    """
    result = compute_study_streak(streak_record)
    assert result == 0, f"Missing streak record must yield 0, got {result}"


@given(current_streak=st.integers(min_value=0, max_value=365))
@settings(max_examples=100)
def test_property18_streak_is_non_negative(current_streak):
    """
    # Feature: learningpath-ai, Property 18: Study streak computation

    compute_study_streak must always return a non-negative integer.

    Validates: Requirements 5.3
    """
    record = {
        "userId": "u1",
        "resourceId": "STREAK#current",
        "currentStreak": current_streak,
        "lastCompletionDate": "2026-07-11",
    }
    result = compute_study_streak(record)
    assert isinstance(result, int), f"Streak must be int, got {type(result)}"
    assert result >= 0, f"Streak must be ≥ 0, got {result}"
