"""
Property-based tests for ProgressTracker Lambda (Properties 18, 19, 20).

# Feature: learningpath-ai, Property 18: Study streak increment and reset
# Feature: learningpath-ai, Property 19: Progress status update persistence
# Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds

Validates: Requirements 6.1, 6.2, 6.4, 6.5, 6.6
"""

import json
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.progress_tracker.handler import (
    MILESTONE_THRESHOLDS,
    STREAK_SORT_KEY,
    VALID_STATUSES,
    compute_completion_percentage,
    handle_put_progress,
    record_milestones_if_crossed,
    reset_streak,
    update_streak,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_user_id_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
    ),
)

_valid_status_strategy = st.sampled_from(sorted(VALID_STATUSES))

_resource_id_uuid = st.uuids().map(lambda u: f"RESOURCE#{u}")

_date_strategy = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2099, 12, 31),
).map(lambda d: d.isoformat())


# ---------------------------------------------------------------------------
# In-memory DynamoDB mock (matches the pattern used in test_resource_properties)
# ---------------------------------------------------------------------------

def _make_mock_db(stored_items=None):
    """Create a mock DynamoDBClient backed by an in-memory dict."""
    db = MagicMock()
    store = {}

    if stored_items:
        for item in stored_items:
            store[(item["userId"], item["resourceId"])] = item

    def put_item(Item):
        store[(Item["userId"], Item["resourceId"])] = Item
        return {}

    def get_item(Key):
        item = store.get((Key["userId"], Key["resourceId"]))
        return {"Item": item} if item else {}

    def delete_item(Key):
        store.pop((Key["userId"], Key["resourceId"]), None)
        return {}

    def query(**kwargs):
        # Return all items in the store (tests control what's in there)
        all_items = list(store.values())
        return {"Items": all_items}

    db.put_item.side_effect = put_item
    db.get_item.side_effect = get_item
    db.delete_item.side_effect = delete_item
    db.query.side_effect = query
    db._store = store
    return db


def _make_resource_item(user_id, resource_id, status="Not Started"):
    """Build a minimal resource DynamoDB item."""
    return {
        "userId": user_id,
        "resourceId": resource_id,
        "title": "Test Resource",
        "url": "https://example.com",
        "resourceType": "Technical Article",
        "learningStatus": status,
        "completionTimestamp": None,
    }


# ===========================================================================
# Property 19: Progress status update persistence
#
# Feature: learningpath-ai, Property 19: Progress status update persistence
# ===========================================================================


@given(
    user_id=_user_id_strategy,
    resource_uuid=st.uuids().map(str),
    new_status=_valid_status_strategy,
)
@settings(max_examples=100)
def test_property19_status_persisted_after_update(user_id, resource_uuid, new_status):
    """
    # Feature: learningpath-ai, Property 19: Progress status update persistence

    For any valid Learning_Status value submitted for a resource, after the
    update, retrieving that resource should reflect the new status.

    Validates: Requirements 6.1, 6.2
    """
    resource_id = f"RESOURCE#{resource_uuid}"
    resource = _make_resource_item(user_id, resource_id)
    db = _make_mock_db([resource])

    result = handle_put_progress(
        user_id=user_id,
        resource_id=resource_id,
        body={"learningStatus": new_status},
        db=db,
        lambda_client=None,
    )

    assert result["statusCode"] == 200, (
        f"Expected 200, got {result['statusCode']} — body: {result.get('body')}"
    )

    # Verify the persisted item has the new status
    stored = db._store.get((user_id, resource_id))
    assert stored is not None, "Resource not found in store after update"
    assert stored["learningStatus"] == new_status, (
        f"Expected learningStatus='{new_status}', got '{stored['learningStatus']}'"
    )


@given(
    user_id=_user_id_strategy,
    resource_uuid=st.uuids().map(str),
    new_status=_valid_status_strategy,
)
@settings(max_examples=100)
def test_property19_response_body_reflects_new_status(user_id, resource_uuid, new_status):
    """
    # Feature: learningpath-ai, Property 19: Progress status update persistence

    The API response body must also reflect the new status — not the old one.

    Validates: Requirements 6.1, 6.2
    """
    resource_id = f"RESOURCE#{resource_uuid}"
    resource = _make_resource_item(user_id, resource_id, status="Not Started")
    db = _make_mock_db([resource])

    result = handle_put_progress(
        user_id=user_id,
        resource_id=resource_id,
        body={"learningStatus": new_status},
        db=db,
        lambda_client=None,
    )

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["learningStatus"] == new_status, (
        f"Response body learningStatus='{body['learningStatus']}', expected '{new_status}'"
    )


@given(
    user_id=_user_id_strategy,
    resource_uuid=st.uuids().map(str),
    invalid_status=st.text(min_size=1, max_size=30).filter(
        lambda s: s not in VALID_STATUSES
    ),
)
@settings(max_examples=100)
def test_property19_invalid_status_returns_400(user_id, resource_uuid, invalid_status):
    """
    # Feature: learningpath-ai, Property 19: Progress status update persistence

    Any Learning_Status value not in the accepted enum must return HTTP 400.

    Validates: Requirements 6.2
    """
    resource_id = f"RESOURCE#{resource_uuid}"
    resource = _make_resource_item(user_id, resource_id)
    db = _make_mock_db([resource])

    result = handle_put_progress(
        user_id=user_id,
        resource_id=resource_id,
        body={"learningStatus": invalid_status},
        db=db,
        lambda_client=None,
    )

    assert result["statusCode"] == 400, (
        f"Expected 400 for invalid status '{invalid_status}', got {result['statusCode']}"
    )
    body = json.loads(result["body"])
    assert body["error"] == "VALIDATION_ERROR"


@given(
    user_id=_user_id_strategy,
    resource_uuid=st.uuids().map(str),
    owner_id=_user_id_strategy,
)
@settings(max_examples=100)
def test_property19_non_owner_update_returns_403(user_id, resource_uuid, owner_id):
    """
    # Feature: learningpath-ai, Property 19: Progress status update persistence

    Ownership check: if the resource belongs to a different userId, return 403.

    Validates: Requirements 6.7
    """
    assume(user_id != owner_id)

    resource_id = f"RESOURCE#{resource_uuid}"
    # Resource is owned by owner_id, but we store it under the attacker's key
    # so that the get_item look-up by attacker returns the owner's record.
    resource = _make_resource_item(owner_id, resource_id)
    db = _make_mock_db()
    # Seed the item under the attacker's lookup key, but with the owner's userId
    db._store[(user_id, resource_id)] = resource

    result = handle_put_progress(
        user_id=user_id,
        resource_id=resource_id,
        body={"learningStatus": "In Progress"},
        db=db,
        lambda_client=None,
    )

    assert result["statusCode"] == 403, (
        f"Expected 403 for non-owner, got {result['statusCode']}"
    )
    body = json.loads(result["body"])
    assert body["error"] == "FORBIDDEN"


@given(
    user_id=_user_id_strategy,
    resource_uuid=st.uuids().map(str),
)
@settings(max_examples=100)
def test_property19_completed_status_records_timestamp(user_id, resource_uuid):
    """
    # Feature: learningpath-ai, Property 19: Progress status update persistence

    When the new status is Completed, a completionTimestamp must be recorded.

    Validates: Requirements 6.3
    """
    resource_id = f"RESOURCE#{resource_uuid}"
    resource = _make_resource_item(user_id, resource_id)
    db = _make_mock_db([resource])

    result = handle_put_progress(
        user_id=user_id,
        resource_id=resource_id,
        body={"learningStatus": "Completed"},
        db=db,
        lambda_client=None,
    )

    assert result["statusCode"] == 200
    stored = db._store.get((user_id, resource_id))
    assert stored is not None
    assert stored.get("completionTimestamp") is not None, (
        "completionTimestamp must be set when status is Completed"
    )


# ===========================================================================
# Property 18: Study streak increment and reset
#
# Feature: learningpath-ai, Property 18: Study streak increment and reset
#
# These tests are complementary to test_dashboard_properties.py and focus on
# the ProgressTracker's streak management logic specifically.
# ===========================================================================


@given(
    user_id=_user_id_strategy,
    current_streak=st.integers(min_value=0, max_value=365),
    last_date=_date_strategy,
)
@settings(max_examples=100)
def test_property18_new_day_increments_streak(user_id, current_streak, last_date):
    """
    # Feature: learningpath-ai, Property 18: Study streak increment and reset

    When a user completes a resource on a calendar day different from
    lastCompletionDate, the streak should increment by 1.

    Validates: Requirements 6.4
    """
    today = date.today().isoformat()
    assume(last_date != today)  # ensure it's a different day

    db = _make_mock_db()
    # Seed an existing streak record
    db._store[(user_id, STREAK_SORT_KEY)] = {
        "userId": user_id,
        "resourceId": STREAK_SORT_KEY,
        "currentStreak": current_streak,
        "lastCompletionDate": last_date,
    }

    update_streak(user_id, db)

    stored = db._store.get((user_id, STREAK_SORT_KEY))
    assert stored is not None, "Streak record must exist after update_streak"
    assert stored["currentStreak"] == current_streak + 1, (
        f"Streak should be {current_streak + 1} after new-day completion, "
        f"got {stored['currentStreak']}"
    )
    assert stored["lastCompletionDate"] == today


@given(
    user_id=_user_id_strategy,
    current_streak=st.integers(min_value=1, max_value=365),
)
@settings(max_examples=100)
def test_property18_same_day_does_not_increment_streak(user_id, current_streak):
    """
    # Feature: learningpath-ai, Property 18: Study streak increment and reset

    When a user completes another resource on the same calendar day as
    lastCompletionDate, the streak must NOT be incremented again.

    Validates: Requirements 6.4
    """
    today = date.today().isoformat()
    db = _make_mock_db()
    db._store[(user_id, STREAK_SORT_KEY)] = {
        "userId": user_id,
        "resourceId": STREAK_SORT_KEY,
        "currentStreak": current_streak,
        "lastCompletionDate": today,
    }

    update_streak(user_id, db)

    stored = db._store.get((user_id, STREAK_SORT_KEY))
    assert stored is not None
    assert stored["currentStreak"] == current_streak, (
        f"Streak must stay at {current_streak} on same-day completion, "
        f"got {stored['currentStreak']}"
    )


@given(user_id=_user_id_strategy)
@settings(max_examples=100)
def test_property18_first_completion_sets_streak_to_one(user_id):
    """
    # Feature: learningpath-ai, Property 18: Study streak increment and reset

    When no streak record exists (first ever completion), update_streak must
    create a record with currentStreak=1.

    Validates: Requirements 6.4
    """
    db = _make_mock_db()  # No streak record seeded

    update_streak(user_id, db)

    stored = db._store.get((user_id, STREAK_SORT_KEY))
    assert stored is not None, "Streak record must be created on first completion"
    assert stored["currentStreak"] == 1, (
        f"First completion must set streak to 1, got {stored['currentStreak']}"
    )
    assert stored["lastCompletionDate"] == date.today().isoformat()


@given(
    user_id=_user_id_strategy,
    current_streak=st.integers(min_value=1, max_value=365),
    last_date=_date_strategy,
)
@settings(max_examples=100)
def test_property18_reset_streak_when_no_completion_today(user_id, current_streak, last_date):
    """
    # Feature: learningpath-ai, Property 18: Study streak increment and reset

    When lastCompletionDate is not today, reset_streak must set currentStreak to 0.

    Validates: Requirements 6.5
    """
    today = date.today().isoformat()
    assume(last_date != today)  # ensure it's a past date

    db = _make_mock_db()
    db._store[(user_id, STREAK_SORT_KEY)] = {
        "userId": user_id,
        "resourceId": STREAK_SORT_KEY,
        "currentStreak": current_streak,
        "lastCompletionDate": last_date,
    }

    reset_streak(user_id, db)

    stored = db._store.get((user_id, STREAK_SORT_KEY))
    assert stored is not None
    assert stored["currentStreak"] == 0, (
        f"Streak must be reset to 0 when last completion was {last_date} (today={today}), "
        f"got {stored['currentStreak']}"
    )


@given(
    user_id=_user_id_strategy,
    current_streak=st.integers(min_value=1, max_value=365),
)
@settings(max_examples=100)
def test_property18_reset_streak_preserves_when_completed_today(user_id, current_streak):
    """
    # Feature: learningpath-ai, Property 18: Study streak increment and reset

    When lastCompletionDate IS today, reset_streak must NOT reset the streak
    (the user already completed a resource today).

    Validates: Requirements 6.5
    """
    today = date.today().isoformat()
    db = _make_mock_db()
    db._store[(user_id, STREAK_SORT_KEY)] = {
        "userId": user_id,
        "resourceId": STREAK_SORT_KEY,
        "currentStreak": current_streak,
        "lastCompletionDate": today,
    }

    reset_streak(user_id, db)

    stored = db._store.get((user_id, STREAK_SORT_KEY))
    assert stored is not None
    assert stored["currentStreak"] == current_streak, (
        f"Streak must remain {current_streak} when user completed today, "
        f"got {stored['currentStreak']}"
    )


@given(
    user_id=_user_id_strategy,
    streak_before=st.integers(min_value=0, max_value=365),
)
@settings(max_examples=100)
def test_property18_streak_is_always_non_negative(user_id, streak_before):
    """
    # Feature: learningpath-ai, Property 18: Study streak increment and reset

    The currentStreak value stored by update_streak or reset_streak must
    always be a non-negative integer.

    Validates: Requirements 6.4, 6.5
    """
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db = _make_mock_db()
    db._store[(user_id, STREAK_SORT_KEY)] = {
        "userId": user_id,
        "resourceId": STREAK_SORT_KEY,
        "currentStreak": streak_before,
        "lastCompletionDate": yesterday,
    }

    # Either increment or reset
    update_streak(user_id, db)
    stored_after_update = db._store[(user_id, STREAK_SORT_KEY)]["currentStreak"]
    assert isinstance(stored_after_update, int) and stored_after_update >= 0, (
        f"currentStreak after update_streak must be non-negative int, got {stored_after_update}"
    )

    # Reset
    reset_streak(user_id, db)
    stored_after_reset = db._store[(user_id, STREAK_SORT_KEY)]["currentStreak"]
    assert isinstance(stored_after_reset, int) and stored_after_reset >= 0, (
        f"currentStreak after reset_streak must be non-negative int, got {stored_after_reset}"
    )


# ===========================================================================
# Property 20: Milestone events recorded at thresholds
#
# Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds
# ===========================================================================


@given(
    user_id=_user_id_strategy,
    old_pct=st.floats(min_value=0.0, max_value=24.9, allow_nan=False),
    new_pct=st.floats(min_value=25.0, max_value=100.0, allow_nan=False),
)
@settings(max_examples=100)
def test_property20_milestone_written_when_threshold_crossed(user_id, old_pct, new_pct):
    """
    # Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds

    When the completion percentage crosses any threshold (25/50/75/100),
    a MILESTONE#<threshold> record must be written to DynamoDB.

    Validates: Requirements 6.6
    """
    db = _make_mock_db()

    record_milestones_if_crossed(user_id, old_pct, new_pct, db)

    crossed = [t for t in MILESTONE_THRESHOLDS if old_pct < t <= new_pct]
    for threshold in crossed:
        key = (user_id, f"MILESTONE#{threshold}")
        assert key in db._store, (
            f"MILESTONE#{threshold} must be written when crossing from {old_pct}% to {new_pct}%"
        )
        record = db._store[key]
        assert record["threshold"] == threshold
        assert record.get("recordedAt") is not None, (
            f"MILESTONE#{threshold} must have a recordedAt timestamp"
        )


@given(
    user_id=_user_id_strategy,
    threshold=st.sampled_from(sorted(MILESTONE_THRESHOLDS)),
    old_pct=st.floats(min_value=0.1, max_value=99.9, allow_nan=False),
)
@settings(max_examples=100)
def test_property20_no_duplicate_milestones_when_threshold_not_crossed(
    user_id, threshold, old_pct
):
    """
    # Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds

    When the new percentage does not cross a threshold (old_pct == new_pct),
    no new MILESTONE record should be written.

    Validates: Requirements 6.6
    """
    db = _make_mock_db()

    # old_pct == new_pct means no threshold crossing
    record_milestones_if_crossed(user_id, old_pct, old_pct, db)

    # No milestone records should exist
    milestone_keys = [(user_id, f"MILESTONE#{t}") for t in MILESTONE_THRESHOLDS]
    for key in milestone_keys:
        assert key not in db._store, (
            f"No MILESTONE record should be written when percentage stays at {old_pct}%"
        )


@given(
    user_id=_user_id_strategy,
    completed_count=st.integers(min_value=0, max_value=20),
    total_non_skipped=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100)
def test_property20_exact_threshold_crossing_triggers_milestone(
    user_id, completed_count, total_non_skipped
):
    """
    # Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds

    For any sequence of resources where adding a completion causes the
    percentage to cross a threshold, a Milestone record for that threshold
    must be written.

    Validates: Requirements 6.6
    """
    assume(completed_count <= total_non_skipped)

    db = _make_mock_db()

    # Build resource list for old state (completed_count - 1 completed)
    old_resources = []
    for i in range(total_non_skipped):
        if i < completed_count - 1:
            old_resources.append({"learningStatus": "Completed"})
        else:
            old_resources.append({"learningStatus": "Not Started"})

    # Build resource list for new state (completed_count completed)
    new_resources = []
    for i in range(total_non_skipped):
        if i < completed_count:
            new_resources.append({"learningStatus": "Completed"})
        else:
            new_resources.append({"learningStatus": "Not Started"})

    old_pct = compute_completion_percentage(old_resources)
    new_pct = compute_completion_percentage(new_resources)

    record_milestones_if_crossed(user_id, old_pct, new_pct, db)

    crossed = [t for t in MILESTONE_THRESHOLDS if old_pct < t <= new_pct]
    for threshold in crossed:
        key = (user_id, f"MILESTONE#{threshold}")
        assert key in db._store, (
            f"MILESTONE#{threshold} must be recorded when crossing from "
            f"{old_pct}% to {new_pct}% "
            f"(completed={completed_count}, total={total_non_skipped})"
        )


@given(
    user_id=_user_id_strategy,
    # Range: already past 100% threshold means crossing can't happen
    old_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    new_pct_delta=st.floats(min_value=0.0, max_value=0.0, allow_nan=False),
)
@settings(max_examples=100)
def test_property20_milestone_record_has_required_fields(
    user_id, old_pct, new_pct_delta
):
    """
    # Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds

    Every Milestone record written must contain userId, resourceId (MILESTONE#<n>),
    threshold, and recordedAt fields.

    Validates: Requirements 6.6
    """
    # Force a 25% threshold crossing
    db = _make_mock_db()
    record_milestones_if_crossed(user_id, 0.0, 25.0, db)

    key = (user_id, "MILESTONE#25")
    if key in db._store:
        record = db._store[key]
        assert "userId" in record, "Milestone record must have userId"
        assert "resourceId" in record, "Milestone record must have resourceId"
        assert record["resourceId"] == "MILESTONE#25"
        assert "threshold" in record, "Milestone record must have threshold"
        assert "recordedAt" in record, "Milestone record must have recordedAt"
        assert record["threshold"] == 25


@given(
    user_id=_user_id_strategy,
    new_pct=st.floats(min_value=100.0, max_value=100.0, allow_nan=False),
)
@settings(max_examples=100)
def test_property20_all_four_milestones_recorded_at_100_percent(user_id, new_pct):
    """
    # Feature: learningpath-ai, Property 20: Milestone events recorded at thresholds

    When crossing from 0% to 100%, all four milestone thresholds (25, 50, 75, 100)
    must be recorded.

    Validates: Requirements 6.6
    """
    db = _make_mock_db()
    record_milestones_if_crossed(user_id, 0.0, 100.0, db)

    for threshold in MILESTONE_THRESHOLDS:
        key = (user_id, f"MILESTONE#{threshold}")
        assert key in db._store, (
            f"MILESTONE#{threshold} must be recorded when percentage goes from 0% to 100%"
        )
