"""
Shared authentication helpers for LearningPath AI Lambda functions.

Extracts user identity from API Gateway Lambda proxy integration events.
Handles both dict and JSON-string formats for the authorizer claims context,
as API Gateway flattens nested objects in authorizer response context.
"""

from __future__ import annotations

import json
from typing import Any


def get_user_id(event: dict[str, Any]) -> str | None:
    """
    Extract the authenticated user ID from the API Gateway event.

    Checks (in order):
      1. requestContext.authorizer.claims.sub (dict — legacy/Cognito format)
      2. requestContext.authorizer.claims as JSON string → parse and get "sub"
      3. requestContext.authorizer.sub (flattened context from custom authorizer)
      4. requestContext.authorizer.userId (fallback)

    Returns None if no user ID can be extracted.
    """
    try:
        authorizer = event["requestContext"]["authorizer"]
    except (KeyError, TypeError):
        return None

    # Try claims.sub (Cognito JWT authorizer format)
    claims = authorizer.get("claims")
    if isinstance(claims, dict):
        sub = claims.get("sub")
        if sub:
            return sub
    elif isinstance(claims, str):
        try:
            parsed = json.loads(claims)
            sub = parsed.get("sub")
            if sub:
                return sub
        except (json.JSONDecodeError, TypeError):
            pass

    # Try flattened sub from custom authorizer context
    sub = authorizer.get("sub")
    if sub:
        return sub

    # Fall back to top-level userId
    user_id = authorizer.get("userId")
    if user_id:
        return user_id

    return None
