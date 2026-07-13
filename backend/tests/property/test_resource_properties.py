"""
Property-based tests for ResourceManager Lambda (Properties 1–5).

# Feature: learningpath-ai, Property 1: Resource persistence round-trip
# Feature: learningpath-ai, Property 2: Resource update round-trip
# Feature: learningpath-ai, Property 3: Resource deletion removes from list
# Feature: learningpath-ai, Property 4: Resource input validation rejects invalid fields
# Feature: learningpath-ai, Property 5: Ownership enforcement returns 403

Validates: Requirements 1.1–1.8
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lambdas.resource_manager.handler import (
    _handle_post,
    _handle_get,
    _handle_put,
    _handle_delete,
    VALID_RESOURCE_TYPES,
    VALID_DIFFICULTY_VALUES,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

non_empty_text = st.text(min_size=1, max_size=100).filter(str.strip)
url_text = st.text(min_size=5, max_size=200, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"),
    whitelist_characters="/:.-_#?=&%",
)).map(lambda s: "https://" + s)

valid_resource_type = st.sampled_from(sorted(VALID_RESOURCE_TYPES))
valid_difficulty = st.sampled_from(sorted(VALID_DIFFICULTY_VALUES))
user_id_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
))

def valid_resource_body_strategy():
    return st.fixed_dictionaries({
        "title": non_empty_text,
        "url": url_text,
        "resourceType": valid_resource_type,
    }, optional={
        "difficulty": valid_difficulty,
        "estimatedDuration": st.text(max_size=50),
        "technology": st.text(max_size=50),
        "tags": st.lists(st.text(max_size=20), max_size=5),
    })

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
        uid = None
        # Extract userId from KeyConditionExpression by inspecting the mock's call
        all_items = [v for v in store.values()]
        return {"Items": [i for i in all_items]}

    db.put_item.side_effect = put_item
    db.get_item.side_effect = get_item
    db.delete_item.side_effect = delete_item
    db.query.side_effect = query
    db._store = store
    return db


# ---------------------------------------------------------------------------
# Property 1: Resource persistence round-trip
# ---------------------------------------------------------------------------

@given(body=valid_resource_body_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property1_resource_persistence_round_trip(body, user_id):
    """
    # Feature: learningpath-ai, Property 1: Resource persistence round-trip

    For any valid resource payload, persisting it and then retrieving the
    resource list for that userId should return a record containing all
    submitted field values.

    Validates: Requirements 1.1, 1.2
    """
    db = _make_mock_db()
    result = _handle_post(user_id, body, db, lambda_client=None)
    assert result["statusCode"] == 201

    created = json.loads(result["body"])
    # The created item should reflect all submitted field values
    assert created["title"] == body["title"]
    assert created["url"] == body["url"]
    assert created["resourceType"] == body["resourceType"]
    if "difficulty" in body:
        assert created["difficulty"] == body["difficulty"]
    assert created["userId"] == user_id
    assert created["resourceId"].startswith("RESOURCE#")


@given(body=valid_resource_body_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property1_persisted_item_visible_in_store(body, user_id):
    """
    # Feature: learningpath-ai, Property 1: Resource persistence round-trip

    After POST, the item must exist in the DynamoDB store under the correct
    userId / resourceId key.

    Validates: Requirements 1.1, 1.2
    """
    db = _make_mock_db()
    result = _handle_post(user_id, body, db, lambda_client=None)
    assert result["statusCode"] == 201

    created = json.loads(result["body"])
    resource_id = created["resourceId"]

    # Verify stored via get_item
    stored = db._store.get((user_id, resource_id))
    assert stored is not None
    assert stored["title"] == body["title"]


# ---------------------------------------------------------------------------
# Property 2: Resource update round-trip
# ---------------------------------------------------------------------------

@given(
    original=valid_resource_body_strategy(),
    update=st.fixed_dictionaries({"title": non_empty_text}),
    user_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property2_resource_update_round_trip(original, update, user_id):
    """
    # Feature: learningpath-ai, Property 2: Resource update round-trip

    For any existing resource and any valid update payload, after applying the
    update, the retrieved resource should reflect all new field values.

    Validates: Requirements 1.3
    """
    db = _make_mock_db()
    # Create first
    create_result = _handle_post(user_id, original, db, lambda_client=None)
    assert create_result["statusCode"] == 201
    resource_id = json.loads(create_result["body"])["resourceId"]

    # Update
    put_result = _handle_put(user_id, resource_id, update, db)
    assert put_result["statusCode"] == 200

    updated = json.loads(put_result["body"])
    assert updated["title"] == update["title"]
    # Original URL must still be present
    assert updated["url"] == original["url"]


@given(
    original=valid_resource_body_strategy(),
    user_id=user_id_strategy,
    new_resource_type=valid_resource_type,
)
@settings(max_examples=100)
def test_property2_resource_type_update_round_trip(original, user_id, new_resource_type):
    """
    # Feature: learningpath-ai, Property 2: Resource update round-trip

    Updating resourceType to any valid value should be reflected in the stored record.

    Validates: Requirements 1.3
    """
    db = _make_mock_db()
    create_result = _handle_post(user_id, original, db, lambda_client=None)
    resource_id = json.loads(create_result["body"])["resourceId"]

    put_result = _handle_put(user_id, resource_id, {"resourceType": new_resource_type}, db)
    assert put_result["statusCode"] == 200
    updated = json.loads(put_result["body"])
    assert updated["resourceType"] == new_resource_type


# ---------------------------------------------------------------------------
# Property 3: Resource deletion removes from list
# ---------------------------------------------------------------------------

@given(body=valid_resource_body_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property3_deletion_removes_resource_from_store(body, user_id):
    """
    # Feature: learningpath-ai, Property 3: Resource deletion removes from list

    For any resource that exists for a userId, after a successful delete,
    listing resources for that userId should not include that resourceId.

    Validates: Requirements 1.4
    """
    db = _make_mock_db()
    create_result = _handle_post(user_id, body, db, lambda_client=None)
    assert create_result["statusCode"] == 201
    resource_id = json.loads(create_result["body"])["resourceId"]

    delete_result = _handle_delete(user_id, resource_id, db)
    assert delete_result["statusCode"] == 204

    # Resource must no longer be in the store
    stored = db._store.get((user_id, resource_id))
    assert stored is None


@given(body=valid_resource_body_strategy(), user_id=user_id_strategy)
@settings(max_examples=100)
def test_property3_second_delete_returns_404(body, user_id):
    """
    # Feature: learningpath-ai, Property 3: Resource deletion removes from list

    Deleting a resource that no longer exists returns 404.

    Validates: Requirements 1.4
    """
    db = _make_mock_db()
    create_result = _handle_post(user_id, body, db, lambda_client=None)
    resource_id = json.loads(create_result["body"])["resourceId"]

    _handle_delete(user_id, resource_id, db)
    second_delete = _handle_delete(user_id, resource_id, db)
    assert second_delete["statusCode"] == 404


# ---------------------------------------------------------------------------
# Property 4: Resource input validation rejects invalid fields
# ---------------------------------------------------------------------------

@given(
    title=st.one_of(st.just(""), st.just(None), st.none()),
    url=non_empty_text,
    resource_type=valid_resource_type,
    user_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property4_missing_title_returns_400(title, url, resource_type, user_id):
    """
    # Feature: learningpath-ai, Property 4: Resource input validation rejects invalid fields

    Any resource payload missing the title field returns HTTP 400.

    Validates: Requirements 1.5
    """
    body = {"url": url, "resourceType": resource_type}
    if title is not None:
        body["title"] = title
    db = _make_mock_db()
    result = _handle_post(user_id, body, db, lambda_client=None)
    assert result["statusCode"] == 400
    data = json.loads(result["body"])
    assert data["error"] == "VALIDATION_ERROR"


@given(
    title=non_empty_text,
    resource_type=valid_resource_type,
    user_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property4_missing_url_returns_400(title, resource_type, user_id):
    """
    # Feature: learningpath-ai, Property 4: Resource input validation rejects invalid fields

    Any resource payload missing the url field returns HTTP 400.

    Validates: Requirements 1.5
    """
    body = {"title": title, "resourceType": resource_type}
    db = _make_mock_db()
    result = _handle_post(user_id, body, db, lambda_client=None)
    assert result["statusCode"] == 400


@given(
    title=non_empty_text,
    url=url_text,
    invalid_type=st.text(min_size=1, max_size=30).filter(
        lambda s: s not in VALID_RESOURCE_TYPES
    ),
    user_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property4_invalid_resource_type_returns_400(title, url, invalid_type, user_id):
    """
    # Feature: learningpath-ai, Property 4: Resource input validation rejects invalid fields

    Any resource payload with an invalid resourceType returns HTTP 400.

    Validates: Requirements 1.7
    """
    body = {"title": title, "url": url, "resourceType": invalid_type}
    db = _make_mock_db()
    result = _handle_post(user_id, body, db, lambda_client=None)
    assert result["statusCode"] == 400


@given(
    title=non_empty_text,
    url=url_text,
    resource_type=valid_resource_type,
    invalid_difficulty=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in VALID_DIFFICULTY_VALUES
    ),
    user_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property4_invalid_difficulty_returns_400(title, url, resource_type, invalid_difficulty, user_id):
    """
    # Feature: learningpath-ai, Property 4: Resource input validation rejects invalid fields

    Any resource payload with an invalid difficulty value returns HTTP 400.

    Validates: Requirements 1.8
    """
    body = {"title": title, "url": url, "resourceType": resource_type, "difficulty": invalid_difficulty}
    db = _make_mock_db()
    result = _handle_post(user_id, body, db, lambda_client=None)
    assert result["statusCode"] == 400


# ---------------------------------------------------------------------------
# Property 5: Ownership enforcement returns 403
# ---------------------------------------------------------------------------

@given(
    body=valid_resource_body_strategy(),
    owner_id=user_id_strategy,
    attacker_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property5_put_by_non_owner_returns_403(body, owner_id, attacker_id):
    """
    # Feature: learningpath-ai, Property 5: Ownership enforcement returns 403

    A PUT request from a different userId than the resource owner returns 403.
    The ownership check fires when the stored item's userId != caller's userId.

    Validates: Requirements 1.6
    """
    assume(owner_id != attacker_id)

    # Create the resource under the owner's userId
    db = _make_mock_db()
    create_result = _handle_post(owner_id, body, db, lambda_client=None)
    assert create_result["statusCode"] == 201
    resource_id = json.loads(create_result["body"])["resourceId"]

    # Seed the same item under the attacker's userId key so get_item returns it,
    # but the stored userId is still the owner's — this triggers the ownership check.
    owner_item = db._store[(owner_id, resource_id)]
    db._store[(attacker_id, resource_id)] = owner_item  # same record, different lookup key

    put_result = _handle_put(attacker_id, resource_id, {"title": "Hacked"}, db)
    assert put_result["statusCode"] == 403
    data = json.loads(put_result["body"])
    assert data["error"] == "FORBIDDEN"


@given(
    body=valid_resource_body_strategy(),
    owner_id=user_id_strategy,
    attacker_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property5_delete_by_non_owner_returns_403(body, owner_id, attacker_id):
    """
    # Feature: learningpath-ai, Property 5: Ownership enforcement returns 403

    A DELETE request from a different userId than the resource owner returns 403.

    Validates: Requirements 1.6
    """
    assume(owner_id != attacker_id)

    db = _make_mock_db()
    create_result = _handle_post(owner_id, body, db, lambda_client=None)
    assert create_result["statusCode"] == 201
    resource_id = json.loads(create_result["body"])["resourceId"]

    # Seed item under attacker's userId key so ownership check fires (not 404)
    owner_item = db._store[(owner_id, resource_id)]
    db._store[(attacker_id, resource_id)] = owner_item

    delete_result = _handle_delete(attacker_id, resource_id, db)
    assert delete_result["statusCode"] == 403


@given(
    body=valid_resource_body_strategy(),
    owner_id=user_id_strategy,
)
@settings(max_examples=100)
def test_property5_owner_can_update_own_resource(body, owner_id):
    """
    # Feature: learningpath-ai, Property 5: Ownership enforcement returns 403

    The actual owner can always update their own resource successfully.

    Validates: Requirements 1.6 (positive case)
    """
    db = _make_mock_db()
    create_result = _handle_post(owner_id, body, db, lambda_client=None)
    assert create_result["statusCode"] == 201
    resource_id = json.loads(create_result["body"])["resourceId"]

    put_result = _handle_put(owner_id, resource_id, {"title": "My Update"}, db)
    assert put_result["statusCode"] == 200
