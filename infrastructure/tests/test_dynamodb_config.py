"""
CDK assertion tests for DynamoDB configuration.

Validates that the LearningPathAI DynamoDB table is configured with:
- On-demand billing mode (BillingMode: PAY_PER_REQUEST)  [Requirement 10.2]
- Point-in-time recovery enabled                          [Requirement 10.2]
- Deletion protection enabled in production              [Requirement 10.5]
- No RemovalPolicy.DESTROY in production                 [Requirement 10.5]

Strategy: Templates are loaded from two sources:
1. Non-production: loaded from cdk.out/LearningPathAiStack.template.json
   (the already-synthesized non-prod template; Docker not required).
2. Production: synthesized at test time using the Python CDK stack directly,
   with CDK_BUNDLING_STACKS set to "" so no Docker bundling occurs.
   For the production variant (is_production=True) we build the stack via
   Python to exercise the production-specific paths.
"""

import json
import os
from pathlib import Path

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template, Match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = Path(__file__).parent.parent / "cdk.out" / "LearningPathAiStack.template.json"


def _load_non_prod_template() -> Template:
    """Load the already-synthesized non-production CloudFormation template."""
    with open(_TEMPLATE_PATH) as f:
        template_json = json.load(f)
    return Template.from_json(template_json)


def _build_prod_template() -> Template:
    """
    Build the production template directly in Python (no Docker).

    The Lambda ``Code.from_asset`` constructs with Docker bundling are skipped
    during synthesis when CDK_BUNDLING_STACKS is set to an empty string, which
    tells CDK not to bundle any stacks.  The resulting template still reflects
    all configuration (DeletionProtectionEnabled, RemovalPolicy, etc.) because
    those are pure CloudFormation properties, not affected by bundling.
    """
    # Disable Docker-based bundling during synthesis.
    os.environ.setdefault("CDK_BUNDLING_STACKS", "")

    from learningpath_ai.learningpath_ai_stack import LearningPathAiStack  # noqa: PLC0415

    app = cdk.App(context={"is_production": True})
    stack = LearningPathAiStack(app, "TestStackProd")
    return Template.from_stack(stack)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def non_prod_template() -> Template:
    """Return the non-production CloudFormation template."""
    return _load_non_prod_template()


@pytest.fixture(scope="module")
def prod_template() -> Template:
    """Return the production CloudFormation template."""
    return _build_prod_template()


# ---------------------------------------------------------------------------
# Test 1 — On-demand capacity (PAY_PER_REQUEST) — Requirement 10.2
# ---------------------------------------------------------------------------

class TestOnDemandBillingMode:
    """DynamoDB table must use on-demand (PAY_PER_REQUEST) billing mode."""

    def test_non_prod_billing_mode_is_pay_per_request(self, non_prod_template: Template):
        """Non-production stack has PAY_PER_REQUEST billing mode."""
        non_prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"BillingMode": "PAY_PER_REQUEST"},
        )

    def test_prod_billing_mode_is_pay_per_request(self, prod_template: Template):
        """Production stack has PAY_PER_REQUEST billing mode."""
        prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"BillingMode": "PAY_PER_REQUEST"},
        )

    def test_provisioned_throughput_not_set(self, non_prod_template: Template):
        """ProvisionedThroughput should not be set when using on-demand mode."""
        # With on-demand mode, ProvisionedThroughput should be absent from
        # the table properties.
        tables = non_prod_template.find_resources(
            "AWS::DynamoDB::Table",
            Match.object_like({"Properties": {"TableName": "LearningPathAI"}}),
        )
        assert len(tables) == 1, "Expected exactly one LearningPathAI table"
        props = list(tables.values())[0]["Properties"]
        assert "ProvisionedThroughput" not in props, (
            "ProvisionedThroughput should not be present in on-demand mode"
        )


# ---------------------------------------------------------------------------
# Test 2 — Point-in-time recovery — Requirement 10.2
# ---------------------------------------------------------------------------

class TestPointInTimeRecovery:
    """DynamoDB table must have point-in-time recovery enabled."""

    def test_non_prod_pitr_enabled(self, non_prod_template: Template):
        """Non-production stack has PITR enabled."""
        non_prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "PointInTimeRecoverySpecification": {
                    "PointInTimeRecoveryEnabled": True,
                }
            },
        )

    def test_prod_pitr_enabled(self, prod_template: Template):
        """Production stack has PITR enabled."""
        prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "PointInTimeRecoverySpecification": {
                    "PointInTimeRecoveryEnabled": True,
                }
            },
        )


# ---------------------------------------------------------------------------
# Test 3 — Deletion protection — Requirement 10.5
# ---------------------------------------------------------------------------

class TestDeletionProtection:
    """In production, DynamoDB deletion protection must be enabled."""

    def test_prod_deletion_protection_enabled(self, prod_template: Template):
        """Production stack has deletion protection enabled."""
        prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"DeletionProtectionEnabled": True},
        )

    def test_non_prod_deletion_protection_disabled(self, non_prod_template: Template):
        """Non-production stack has deletion protection disabled (expected)."""
        non_prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"DeletionProtectionEnabled": False},
        )


# ---------------------------------------------------------------------------
# Test 4 — RemovalPolicy — Requirement 10.5
# ---------------------------------------------------------------------------

class TestRemovalPolicy:
    """In production, stateful resources must not use RemovalPolicy.DESTROY."""

    def test_prod_table_removal_policy_is_retain(self, prod_template: Template):
        """Production DynamoDB table must use DeletionPolicy: Retain."""
        tables = prod_template.find_resources(
            "AWS::DynamoDB::Table",
            Match.object_like({"Properties": {"TableName": "LearningPathAI"}}),
        )
        assert len(tables) == 1, "Expected exactly one LearningPathAI table"
        resource = list(tables.values())[0]
        deletion_policy = resource.get("DeletionPolicy", "")
        update_replace_policy = resource.get("UpdateReplacePolicy", "")
        assert deletion_policy == "Retain", (
            f"Production table DeletionPolicy must be 'Retain', got '{deletion_policy}'"
        )
        assert update_replace_policy == "Retain", (
            f"Production table UpdateReplacePolicy must be 'Retain', got '{update_replace_policy}'"
        )

    def test_non_prod_table_removal_policy_is_delete(self, non_prod_template: Template):
        """Non-production DynamoDB table uses DeletionPolicy: Delete (expected)."""
        tables = non_prod_template.find_resources(
            "AWS::DynamoDB::Table",
            Match.object_like({"Properties": {"TableName": "LearningPathAI"}}),
        )
        assert len(tables) == 1, "Expected exactly one LearningPathAI table"
        resource = list(tables.values())[0]
        deletion_policy = resource.get("DeletionPolicy", "")
        assert deletion_policy == "Delete", (
            f"Non-production table DeletionPolicy must be 'Delete', got '{deletion_policy}'"
        )


# ---------------------------------------------------------------------------
# Test 5 — Table name and key schema sanity checks
# ---------------------------------------------------------------------------

class TestTableSchema:
    """Verify the table has the correct name and key schema."""

    def test_table_name(self, non_prod_template: Template):
        """Table name must be 'LearningPathAI'."""
        non_prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "LearningPathAI"},
        )

    def test_partition_key(self, non_prod_template: Template):
        """Partition key must be 'userId' (String)."""
        non_prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "KeySchema": Match.array_with([
                    {"AttributeName": "userId", "KeyType": "HASH"},
                ])
            },
        )

    def test_sort_key(self, non_prod_template: Template):
        """Sort key must be 'resourceId' (String)."""
        non_prod_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "KeySchema": Match.array_with([
                    {"AttributeName": "resourceId", "KeyType": "RANGE"},
                ])
            },
        )

    def test_exactly_one_dynamodb_table(self, non_prod_template: Template):
        """Stack must provision exactly one DynamoDB table."""
        non_prod_template.resource_count_is("AWS::DynamoDB::Table", 1)
