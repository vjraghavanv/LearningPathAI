#!/usr/bin/env python3
"""CDK app entry point for LearningPath AI infrastructure."""

import aws_cdk as cdk

from learningpath_ai.learningpath_ai_stack import LearningPathAiStack

app = cdk.App()

LearningPathAiStack(
    app,
    "LearningPathAiStack",
    description="LearningPath AI — serverless AWS-native learning productivity application",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
)

app.synth()
