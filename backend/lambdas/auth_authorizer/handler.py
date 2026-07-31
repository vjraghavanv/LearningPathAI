"""
Lambda Authorizer for LearningPath AI API Gateway.

Validates the Authorization header on incoming requests. Returns an IAM
policy that either ALLOWs or DENYs access. API Gateway returns HTTP 401
automatically when the authorizer returns a Deny policy or raises an
Unauthorized exception.

Strategy:
  - If no Authorization header is present → Deny (API GW returns 401)
  - If the token does not have the expected format (Bearer <token>) → Deny
  - If the token value is present and non-empty → Allow
    (In production, replace the stub validation with a real JWT verify step
    against your Cognito User Pool or third-party identity provider.)

The authorizer is configured as a TOKEN-type Lambda authorizer on the
API Gateway, which passes the Authorization header value as the ``authorizationToken``
field of the event.

Requirement references: 9.2, 12.5
"""

from __future__ import annotations

import os
import re
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Expected token prefix (Bearer scheme)
_BEARER_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)

# Optional: a hard-coded test token for non-production environments.
# In production this would be replaced by real JWT verification.
_DEV_TOKEN: str = os.environ.get("DEV_AUTH_TOKEN", "")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda Authorizer handler — evaluates the Authorization header.

    API Gateway TOKEN-type authorizer contract:
      - event["authorizationToken"] — the raw Authorization header value
      - event["methodArn"]           — the ARN of the method being invoked

    Returns an IAM policy document with either Allow or Deny effect.
    """
    token: str = event.get("authorizationToken") or ""
    method_arn: str = event.get("methodArn") or "*"

    principal_id, effect = _validate_token(token)

    policy = _build_policy(principal_id=principal_id, effect=effect, resource=method_arn)

    # Include a context object so downstream Lambda can read the userId
    # API Gateway only allows string, number, or boolean values in context (no nested objects)
    policy["context"] = {
        "userId": principal_id if effect == "Allow" else "",
        "sub": principal_id if effect == "Allow" else "",
    }

    return policy


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def _validate_token(raw_token: str) -> tuple[str, str]:
    """
    Validate the raw Authorization header value.

    Returns:
        (principal_id, effect) where effect is "Allow" or "Deny".
    """
    if not raw_token:
        return "anonymous", "Deny"

    match = _BEARER_PATTERN.match(raw_token.strip())
    if not match:
        return "anonymous", "Deny"

    token_value = match.group(1).strip()
    if not token_value:
        return "anonymous", "Deny"

    # In a real implementation, verify the JWT signature and expiry here.
    # For development/testing purposes we accept any non-empty Bearer token.
    # The principal_id would normally be the JWT ``sub`` claim.
    principal_id = _extract_principal(token_value)

    return principal_id, "Allow"


def _extract_principal(token_value: str) -> str:
    """
    Extract a principal identifier from the token.

    In production this would decode and verify a JWT, extracting the ``sub``
    claim. For the stub implementation we return a hash-like identifier so
    that the principal is deterministic for the same token.
    """
    # Stub: use the first 36 characters as a pseudo-userId, or the whole value
    return token_value[:36] if len(token_value) >= 36 else token_value


# ---------------------------------------------------------------------------
# IAM policy builder
# ---------------------------------------------------------------------------

def _build_policy(principal_id: str, effect: str, resource: str) -> dict[str, Any]:
    """
    Build an API Gateway IAM policy response.

    Args:
        principal_id: Identifier for the caller (e.g. JWT sub claim).
        effect:       "Allow" or "Deny".
        resource:     The method ARN to grant/deny access to.
                      Using "*" grants/denies all methods in the API.

    Returns:
        A dict matching the API Gateway authorizer response contract.
    """
    # Use a wildcard resource so a single authorizer covers all endpoints.
    # Derive the base API ARN from the method ARN: arn:...:api-id/stage/*
    base_arn = _base_arn(resource)

    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": base_arn,
                }
            ],
        },
    }


def _base_arn(method_arn: str) -> str:
    """
    Derive a wildcard ARN covering all methods in the same API stage.

    Transforms:
        arn:aws:execute-api:region:account:api-id/stage/METHOD/resource
      → arn:aws:execute-api:region:account:api-id/stage/*

    Falls back to "*" if the ARN cannot be parsed.
    """
    parts = method_arn.split(":")
    if len(parts) >= 6:
        # parts[5] looks like "api-id/stage/METHOD/resource"
        path_parts = parts[5].split("/")
        if len(path_parts) >= 2:
            base = "/".join(path_parts[:2])
            parts[5] = base + "/*"
            return ":".join(parts)
    return "*"
