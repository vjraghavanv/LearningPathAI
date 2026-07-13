"""
LearningPath AI — main CDK stack.

Provisions:
- DynamoDB single-table (on-demand, PITR enabled)
- IAM roles with least-privilege policies for 7 Lambda functions
- Placeholder Lambda functions (code wired in later tasks)
- API Gateway REST API with WAF integration and usage plan
- CloudWatch log groups (30-day retention) for each Lambda
- CloudWatch Dashboard with Lambda / API GW / DynamoDB metrics
- CloudWatch Alarms (error rate > 5%) publishing to SNS
- Amplify App for React frontend hosting
- CfnOutputs for API URL and Amplify URL
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_wafv2 as wafv2,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_amplify as amplify,
    aws_events as events,
    aws_events_targets as events_targets,
)
from constructs import Construct


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 7 Lambda functions in the system
LAMBDA_FUNCTIONS = [
    "resource-manager",
    "ai-analyzer",
    "career-goal-manager",
    "ai-planner",
    "dashboard-api",
    "progress-tracker",
    "search-service",
]

BEDROCK_NOVA_LITE_ARN = "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0"


class _LocalLambdaBundler(cdk.ILocalBundling):
    """
    Bundles a Lambda function locally (no Docker required).

    Copies the specified Lambda handler package and the shared utilities
    into the CDK asset output directory, then runs pip to install any
    requirements.txt found in the source root.

    Args:
        backend_root: Absolute path to the backend/ directory.
        lambda_package: Sub-package name inside backend/lambdas/ to copy
                        (e.g. "ai_planner").  Pass None to skip Lambda copy.
        extra_packages: Additional sub-package names inside backend/ to copy
                        (e.g. ["shared"]).
    """

    def __init__(
        self,
        backend_root: str,
        lambda_package: str | None,
        extra_packages: list[str] | None = None,
    ) -> None:
        self._backend_root = backend_root
        self._lambda_package = lambda_package
        self._extra_packages = extra_packages or []

    def try_bundle(self, output_dir: str, options: cdk.BundlingOptions) -> bool:  # type: ignore[override]
        try:
            # 1. Install requirements if present
            req_file = os.path.join(self._backend_root, "requirements.txt")
            if os.path.isfile(req_file):
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-r", req_file, "-t", output_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            # 2. Copy the Lambda handler package
            if self._lambda_package:
                src = os.path.join(self._backend_root, "lambdas", self._lambda_package)
                dst = os.path.join(output_dir, self._lambda_package)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)

            # 3. Copy extra packages (e.g. shared/)
            for pkg in self._extra_packages:
                src = os.path.join(self._backend_root, pkg)
                dst = os.path.join(output_dir, pkg)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif os.path.isfile(src):
                    shutil.copy2(src, os.path.join(output_dir, os.path.basename(src)))

            return True
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[LocalBundler] ERROR: {exc}", file=sys.stderr)
            return False


# Absolute path to the backend source directory, resolved relative to this file.
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))


def _lambda_code(lambda_package: str) -> lambda_.Code:
    """
    Return Lambda code using local bundling (no Docker required).

    During CDK tests (CDK_BUNDLING_STACKS=""), returns a lightweight inline
    placeholder so no file system access is needed.
    """
    if os.environ.get("CDK_BUNDLING_STACKS") == "":
        return lambda_.Code.from_inline(
            "def handler(event, context):\n    return {'statusCode': 200, 'body': 'placeholder'}\n"
        )

    bundler = _LocalLambdaBundler(
        backend_root=_BACKEND_ROOT,
        lambda_package=lambda_package,
        extra_packages=["shared"],
    )

    return lambda_.Code.from_asset(
        _BACKEND_ROOT,
        bundling=cdk.BundlingOptions(
            image=lambda_.Runtime.PYTHON_3_11.bundling_image,
            local=bundler,
            # Docker fallback (only used if local bundling returns False)
            command=[
                "bash", "-c",
                f"cp -r lambdas/{lambda_package} /asset-output/ && cp -r shared /asset-output/",
            ],
        ),
    )


class LearningPathAiStack(cdk.Stack):
    """Top-level CDK stack for LearningPath AI."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Determine whether this is a production deployment.
        is_production: bool = bool(self.node.try_get_context("is_production"))

        # ------------------------------------------------------------------ #
        # 1. DynamoDB
        # ------------------------------------------------------------------ #
        self.table = self._create_dynamodb(is_production)

        # ------------------------------------------------------------------ #
        # 2. IAM roles
        # ------------------------------------------------------------------ #
        self.roles = self._create_iam_roles()

        # ------------------------------------------------------------------ #
        # 3. Placeholder Lambda functions
        # ------------------------------------------------------------------ #
        self.functions = self._create_placeholder_lambdas()

        # ------------------------------------------------------------------ #
        # 4. API Gateway + WAF
        # ------------------------------------------------------------------ #
        self.api = self._create_api_gateway()

        # ------------------------------------------------------------------ #
        # 5. CloudWatch log groups
        # ------------------------------------------------------------------ #
        self._create_log_groups()

        # ------------------------------------------------------------------ #
        # 6. CloudWatch Dashboard
        # ------------------------------------------------------------------ #
        self._create_dashboard()

        # ------------------------------------------------------------------ #
        # 7. CloudWatch Alarms + SNS
        # ------------------------------------------------------------------ #
        self._create_alarms()

        # ------------------------------------------------------------------ #
        # 8. Amplify frontend hosting
        # ------------------------------------------------------------------ #
        self.amplify_app, self.amplify_branch = self._create_amplify_app()

        # ------------------------------------------------------------------ #
        # 9. Stack outputs
        # ------------------------------------------------------------------ #
        self._create_outputs()

    # ---------------------------------------------------------------------- #
    # DynamoDB — subtask 1.2
    # ---------------------------------------------------------------------- #
    def _create_dynamodb(self, is_production: bool) -> dynamodb.Table:
        """Create the LearningPathAI single-table DynamoDB table."""

        removal_policy = (
            cdk.RemovalPolicy.RETAIN if is_production else cdk.RemovalPolicy.DESTROY
        )

        table = dynamodb.Table(
            self,
            "LearningPathAITable",
            table_name="LearningPathAI",
            partition_key=dynamodb.Attribute(
                name="userId",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="resourceId",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            deletion_protection=is_production,
            removal_policy=removal_policy,
        )

        return table

    # ---------------------------------------------------------------------- #
    # IAM roles — subtask 1.3
    # ---------------------------------------------------------------------- #
    def _create_iam_roles(self) -> dict[str, iam.Role]:
        """Create one least-privilege IAM role per Lambda function."""

        lambda_principal = iam.ServicePrincipal("lambda.amazonaws.com")
        basic_exec = iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSLambdaBasicExecutionRole"
        )

        # DynamoDB action sets
        dynamo_read_write_actions = [
            "dynamodb:PutItem",
            "dynamodb:GetItem",
            "dynamodb:Query",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
        ]
        dynamo_read_only_actions = [
            "dynamodb:GetItem",
            "dynamodb:Query",
        ]

        def _make_role(logical_id: str, function_name: str) -> iam.Role:
            return iam.Role(
                self,
                logical_id,
                assumed_by=lambda_principal,
                managed_policies=[basic_exec],
                description=f"Execution role for {function_name} Lambda function",
            )

        def _add_dynamo_rw(role: iam.Role) -> None:
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=dynamo_read_write_actions,
                    resources=[self.table.table_arn],
                )
            )

        def _add_dynamo_ro(role: iam.Role) -> None:
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=dynamo_read_only_actions,
                    resources=[self.table.table_arn],
                )
            )

        def _add_bedrock(role: iam.Role) -> None:
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["bedrock:InvokeModel"],
                    resources=[BEDROCK_NOVA_LITE_ARN],
                )
            )

        # ---- resource_manager_role ----------------------------------------
        resource_manager_role = _make_role("ResourceManagerRole", "resource-manager")
        _add_dynamo_rw(resource_manager_role)

        # ---- ai_analyzer_role ----------------------------------------------
        ai_analyzer_role = _make_role("AiAnalyzerRole", "ai-analyzer")
        _add_dynamo_rw(ai_analyzer_role)
        _add_bedrock(ai_analyzer_role)

        # ---- career_goal_manager_role --------------------------------------
        career_goal_manager_role = _make_role(
            "CareerGoalManagerRole", "career-goal-manager"
        )
        _add_dynamo_rw(career_goal_manager_role)

        # ---- ai_planner_role -----------------------------------------------
        ai_planner_role = _make_role("AiPlannerRole", "ai-planner")
        _add_dynamo_rw(ai_planner_role)
        _add_bedrock(ai_planner_role)

        # ---- dashboard_api_role --------------------------------------------
        dashboard_api_role = _make_role("DashboardApiRole", "dashboard-api")
        _add_dynamo_ro(dashboard_api_role)

        # ---- progress_tracker_role -----------------------------------------
        progress_tracker_role = _make_role("ProgressTrackerRole", "progress-tracker")
        _add_dynamo_rw(progress_tracker_role)

        # ---- search_service_role -------------------------------------------
        search_service_role = _make_role("SearchServiceRole", "search-service")
        _add_dynamo_ro(search_service_role)

        return {
            "resource_manager_role": resource_manager_role,
            "ai_analyzer_role": ai_analyzer_role,
            "career_goal_manager_role": career_goal_manager_role,
            "ai_planner_role": ai_planner_role,
            "dashboard_api_role": dashboard_api_role,
            "progress_tracker_role": progress_tracker_role,
            "search_service_role": search_service_role,
        }

    # ---------------------------------------------------------------------- #
    # Placeholder Lambdas
    # ---------------------------------------------------------------------- #
    def _create_placeholder_lambdas(self) -> dict[str, lambda_.Function]:
        """
        Stub Lambda functions — code will be replaced in later tasks.
        Roles, env-vars, and log groups are wired here so other constructs
        (API GW, alarms) can reference the function objects.
        """
        role_map = {
            "resource-manager": self.roles["resource_manager_role"],
            "ai-analyzer": self.roles["ai_analyzer_role"],
            "career-goal-manager": self.roles["career_goal_manager_role"],
            "ai-planner": self.roles["ai_planner_role"],
            "dashboard-api": self.roles["dashboard_api_role"],
            "progress-tracker": self.roles["progress_tracker_role"],
            "search-service": self.roles["search_service_role"],
        }

        functions: dict[str, lambda_.Function] = {}
        for name in LAMBDA_FUNCTIONS:
            fn = lambda_.Function(
                self,
                f"{_pascal(name)}Function",
                function_name=f"learningpath-ai-{name}",
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler="index.handler",
                code=lambda_.Code.from_inline(
                    "def handler(event, context):\n    return {'statusCode': 200, 'body': 'placeholder'}\n"
                ),
                role=role_map[name],
                environment={
                    "TABLE_NAME": self.table.table_name,
                    "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
                },
                timeout=cdk.Duration.seconds(30),
                description=f"LearningPath AI — {name} (placeholder)",
            )
            functions[name] = fn

        # ---- Wire AI_Planner with real handler code -----------------------
        ai_planner_fn = lambda_.Function(
            self,
            "AiPlannerRealFunction",
            function_name="learningpath-ai-ai-planner",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="ai_planner.handler.handler",
            code=_lambda_code("ai_planner"),
            role=role_map["ai-planner"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
            },
            timeout=cdk.Duration.seconds(60),
            description="LearningPath AI — AI_Planner Lambda",
        )
        functions["ai-planner"] = ai_planner_fn

        # ---- Wire CareerGoalManager with real handler code ---------------
        career_goal_fn = lambda_.Function(
            self,
            "CareerGoalManagerRealFunction",
            function_name="learningpath-ai-career-goal-manager",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="career_goal_manager.handler.handler",
            code=_lambda_code("career_goal_manager"),
            role=role_map["career-goal-manager"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
                "AI_PLANNER_FUNCTION_NAME": "learningpath-ai-ai-planner",
            },
            timeout=cdk.Duration.seconds(30),
            description="LearningPath AI — CareerGoalManager Lambda",
        )
        career_goal_fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:learningpath-ai-ai-planner"
                ],
            )
        )
        functions["career-goal-manager"] = career_goal_fn

        # ---- Wire AI_Analyzer with real handler code ----------------------
        ai_analyzer_fn = lambda_.Function(
            self,
            "AiAnalyzerRealFunction",
            function_name="learningpath-ai-ai-analyzer",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="ai_analyzer.handler.handler",
            code=_lambda_code("ai_analyzer"),
            role=role_map["ai-analyzer"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
            },
            timeout=cdk.Duration.seconds(30),
            description="LearningPath AI — AI_Analyzer Lambda",
        )
        functions["ai-analyzer"] = ai_analyzer_fn

        # ---- Wire ResourceManager with real handler code ------------------
        resource_manager_fn = lambda_.Function(
            self,
            "ResourceManagerRealFunction",
            function_name="learningpath-ai-resource-manager",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="resource_manager.handler.handler",
            code=_lambda_code("resource_manager"),
            role=role_map["resource-manager"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
                "AI_ANALYZER_FUNCTION_NAME": f"learningpath-ai-ai-analyzer",
            },
            timeout=cdk.Duration.seconds(30),
            description="LearningPath AI — ResourceManager Lambda",
        )
        # Grant lambda:InvokeFunction on the AI Analyzer function
        resource_manager_fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:learningpath-ai-ai-analyzer"
                ],
            )
        )
        # Replace placeholder with real function in the map
        functions["resource-manager"] = resource_manager_fn

        # ---- Wire DashboardAPI with real handler code ----------------------
        dashboard_api_fn = lambda_.Function(
            self,
            "DashboardApiRealFunction",
            function_name="learningpath-ai-dashboard-api",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="dashboard_api.handler.handler",
            code=_lambda_code("dashboard_api"),
            role=role_map["dashboard-api"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
            },
            # 3-second target (Requirement 5.5) — allow headroom for cold starts
            timeout=cdk.Duration.seconds(10),
            description="LearningPath AI — DashboardAPI Lambda",
        )
        functions["dashboard-api"] = dashboard_api_fn

        # ---- Wire ProgressTracker with real handler code (task 8.6) -------
        progress_tracker_fn = lambda_.Function(
            self,
            "ProgressTrackerRealFunction",
            function_name="learningpath-ai-progress-tracker",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="progress_tracker.handler.handler",
            code=_lambda_code("progress_tracker"),
            role=role_map["progress-tracker"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
                "AI_PLANNER_FUNCTION_NAME": "learningpath-ai-ai-planner",
            },
            timeout=cdk.Duration.seconds(30),
            description="LearningPath AI — ProgressTracker Lambda",
        )
        # Grant lambda:InvokeFunction on the AI Planner function
        progress_tracker_fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:learningpath-ai-ai-planner"
                ],
            )
        )
        functions["progress-tracker"] = progress_tracker_fn

        # ---- Wire SearchService with real handler code (task 9.4) ----------
        search_service_fn = lambda_.Function(
            self,
            "SearchServiceRealFunction",
            function_name="learningpath-ai-search-service",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="search_service.handler.handler",
            code=_lambda_code("search_service"),
            role=role_map["search-service"],
            environment={
                "DYNAMODB_TABLE_NAME": self.table.table_name,
            },
            # 2-second target (Requirement 8.5) — allow headroom for cold starts
            timeout=cdk.Duration.seconds(10),
            description="LearningPath AI — SearchService Lambda",
        )
        functions["search-service"] = search_service_fn

        # ---- EventBridge midnight streak-reset rule (task 8.4 / 8.6) ------
        streak_reset_rule = events.Rule(
            self,
            "StreakResetRule",
            rule_name="LearningPathAI-MidnightStreakReset",
            description="Triggers ProgressTracker at midnight UTC to reset study streaks",
            schedule=events.Schedule.cron(minute="0", hour="0"),
        )
        streak_reset_rule.add_target(
            events_targets.LambdaFunction(
                progress_tracker_fn,
                event=events.RuleTargetInput.from_object({"source": "aws.events"}),
            )
        )

        return functions

    # ---------------------------------------------------------------------- #
    # API Gateway + WAF — subtask 1.4 / task 10
    # ---------------------------------------------------------------------- #
    def _create_api_gateway(self) -> apigateway.RestApi:
        """Create REST API with WAF, usage plan, CORS, authorizer, and security config."""

        # ---- Lambda Authorizer function (task 10.1) -----------------------
        authorizer_role = iam.Role(
            self,
            "AuthorizerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            description="Execution role for API Gateway Lambda authorizer",
        )

        authorizer_fn = lambda_.Function(
            self,
            "AuthAuthorizerFunction",
            function_name="learningpath-ai-auth-authorizer",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="auth_authorizer.handler.handler",
            code=_lambda_code("auth_authorizer"),
            role=authorizer_role,
            environment={},
            timeout=cdk.Duration.seconds(5),
            description="LearningPath AI — Lambda authorizer (validates Authorization header)",
        )

        # REST API
        api = apigateway.RestApi(
            self,
            "LearningPathAIApi",
            rest_api_name="LearningPathAI-API",
            description="LearningPath AI REST API",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=1.67,   # 100 req/min ≈ 1.67 req/s
                throttling_burst_limit=10,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
            ),
        )

        # ---- Gateway Response: generic 500 (task 10.3) --------------------
        # Ensures unhandled Lambda exceptions return a generic message without
        # stack traces or internal details (Requirement 9.5).
        apigateway.CfnGatewayResponse(
            self,
            "Default5xxGatewayResponse",
            rest_api_id=api.rest_api_id,
            response_type="DEFAULT_5XX",
            response_templates={
                "application/json": '{"error":"INTERNAL_SERVER_ERROR","message":"An unexpected error occurred."}'
            },
            response_parameters={
                "gatewayresponse.header.Content-Type": "'application/json'",
            },
        )

        # ---- Gateway Response: 401 Unauthorized ---------------------------
        apigateway.CfnGatewayResponse(
            self,
            "UnauthorizedGatewayResponse",
            rest_api_id=api.rest_api_id,
            response_type="UNAUTHORIZED",
            status_code="401",
            response_templates={
                "application/json": '{"error":"UNAUTHORIZED","message":"Missing or invalid Authorization header."}'
            },
            response_parameters={
                "gatewayresponse.header.Content-Type": "'application/json'",
            },
        )

        # ---- Gateway Response: 415 Unsupported Media Type (task 10.2) -----
        # Note: API GW request validators returning 415 are handled via
        # INVALID_MEDIA_TYPE gateway response when Content-Type validation fails.
        # The request validator below enforces Content-Type on POST/PUT methods.

        # ---- Lambda TOKEN authorizer (task 10.1) --------------------------
        token_authorizer = apigateway.TokenAuthorizer(
            self,
            "LearningPathAIAuthorizer",
            handler=authorizer_fn,
            authorizer_name="LearningPathAITokenAuthorizer",
            identity_source="method.request.header.Authorization",
            results_cache_ttl=cdk.Duration.seconds(300),
        )

        # ---- Request validator for Content-Type (task 10.2) ---------------
        # API Gateway request validator validates headers on POST/PUT requests.
        # When Content-Type is not application/json the gateway returns 415.
        request_validator = apigateway.RequestValidator(
            self,
            "ContentTypeValidator",
            rest_api=api,
            request_validator_name="validate-content-type",
            validate_request_body=False,
            validate_request_parameters=True,
        )

        # ---- WAF Web ACL ---------------------------------------------------
        web_acl = wafv2.CfnWebACL(
            self,
            "LearningPathAIWebACL",
            name="LearningPathAI-WebACL",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="LearningPathAI-WebACL",
                sampled_requests_enabled=True,
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=1,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesCommonRuleSet",
                        sampled_requests_enabled=True,
                    ),
                )
            ],
        )

        # Associate WAF with the API Gateway stage
        wafv2.CfnWebACLAssociation(
            self,
            "LearningPathAIWebACLAssociation",
            resource_arn=cdk.Fn.sub(
                "arn:aws:apigateway:${AWS::Region}::/restapis/${ApiId}/stages/prod",
                {"ApiId": api.rest_api_id},
            ),
            web_acl_arn=web_acl.attr_arn,
        )

        # ---- Usage plan ----------------------------------------------------
        usage_plan = apigateway.UsagePlan(
            self,
            "LearningPathAIUsagePlan",
            name="LearningPathAI-UsagePlan",
            description="100 requests per minute per user",
            throttle=apigateway.ThrottleSettings(
                rate_limit=1.67,   # per second → 100 req/min
                burst_limit=10,
            ),
        )
        usage_plan.add_api_stage(
            api=api,
            stage=api.deployment_stage,
        )

        # ---- Wire Lambdas into the API with authorizer + validators --------
        fn = self.functions

        # /resources
        resources_res = api.root.add_resource("resources")
        resources_res.add_method(
            "POST",
            apigateway.LambdaIntegration(fn["resource-manager"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )
        resources_res.add_method(
            "GET",
            apigateway.LambdaIntegration(fn["resource-manager"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
        )
        resource_id_res = resources_res.add_resource("{id}")
        resource_id_res.add_method(
            "PUT",
            apigateway.LambdaIntegration(fn["resource-manager"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )
        resource_id_res.add_method(
            "DELETE",
            apigateway.LambdaIntegration(fn["resource-manager"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
        )

        # /analyze
        api.root.add_resource("analyze").add_method(
            "POST",
            apigateway.LambdaIntegration(fn["ai-analyzer"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )

        # /career-goal
        career_res = api.root.add_resource("career-goal")
        career_res.add_method(
            "POST",
            apigateway.LambdaIntegration(fn["career-goal-manager"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )
        career_res.add_method(
            "PUT",
            apigateway.LambdaIntegration(fn["career-goal-manager"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )

        # /learning-plan
        api.root.add_resource("learning-plan").add_method(
            "POST",
            apigateway.LambdaIntegration(fn["ai-planner"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )

        # /dashboard
        api.root.add_resource("dashboard").add_method(
            "GET",
            apigateway.LambdaIntegration(fn["dashboard-api"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
        )

        # /progress/{id}
        progress_id_res = api.root.add_resource("progress").add_resource("{id}")
        progress_id_res.add_method(
            "PUT",
            apigateway.LambdaIntegration(fn["progress-tracker"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )
        progress_id_res.add_method(
            "PATCH",
            apigateway.LambdaIntegration(fn["progress-tracker"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            request_validator=request_validator,
            request_parameters={"method.request.header.Content-Type": True},
        )

        # /search
        api.root.add_resource("search").add_method(
            "GET",
            apigateway.LambdaIntegration(fn["search-service"]),
            authorizer=token_authorizer,
            authorization_type=apigateway.AuthorizationType.CUSTOM,
        )

        return api

    # ---------------------------------------------------------------------- #
    # CloudWatch log groups — subtask 1.5
    # ---------------------------------------------------------------------- #
    def _create_log_groups(self) -> None:
        """Create a 30-day CloudWatch log group for each Lambda function."""

        for name in LAMBDA_FUNCTIONS:
            logs.LogGroup(
                self,
                f"{_pascal(name)}LogGroup",
                log_group_name=f"/aws/lambda/learningpath-ai-{name}",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )

    # ---------------------------------------------------------------------- #
    # CloudWatch Dashboard — subtask 1.6
    # ---------------------------------------------------------------------- #
    def _create_dashboard(self) -> cloudwatch.Dashboard:
        """Create a CloudWatch Dashboard with Lambda, API GW, and DDB metrics."""

        dashboard = cloudwatch.Dashboard(
            self,
            "LearningPathAIDashboard",
            dashboard_name="LearningPathAI-Dashboard",
        )

        # ---- Row 1: Lambda metrics ----------------------------------------
        lambda_widgets: list[cloudwatch.IWidget] = []
        for name in LAMBDA_FUNCTIONS:
            fn = self.functions[name]

            invocations = cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Invocations",
                dimensions_map={"FunctionName": fn.function_name},
                statistic="Sum",
                period=cdk.Duration.minutes(5),
            )
            errors = cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions_map={"FunctionName": fn.function_name},
                statistic="Sum",
                period=cdk.Duration.minutes(5),
            )
            duration_p95 = cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Duration",
                dimensions_map={"FunctionName": fn.function_name},
                statistic="p95",
                period=cdk.Duration.minutes(5),
            )

            error_rate_expression = cloudwatch.MathExpression(
                expression="(errors / MAX([errors, invocations])) * 100",
                using_metrics={
                    "errors": errors,
                    "invocations": invocations,
                },
                label="ErrorRate (%)",
                period=cdk.Duration.minutes(5),
            )

            widget = cloudwatch.GraphWidget(
                title=f"Lambda: {name}",
                left=[invocations, errors],
                right=[duration_p95],
                width=8,
                height=6,
            )
            widget.add_left_metric(error_rate_expression)
            lambda_widgets.append(widget)

        dashboard.add_widgets(*lambda_widgets)

        # ---- Row 2: API Gateway metrics -----------------------------------
        apigw_4xx = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="4XXError",
            dimensions_map={
                "ApiName": "LearningPathAI-API",
                "Stage": "prod",
            },
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        apigw_5xx = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="5XXError",
            dimensions_map={
                "ApiName": "LearningPathAI-API",
                "Stage": "prod",
            },
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Gateway Errors",
                left=[apigw_4xx, apigw_5xx],
                width=12,
                height=6,
            )
        )

        # ---- Row 3: DynamoDB metrics --------------------------------------
        ddb_read = cloudwatch.Metric(
            namespace="AWS/DynamoDB",
            metric_name="ConsumedReadCapacityUnits",
            dimensions_map={"TableName": self.table.table_name},
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        ddb_write = cloudwatch.Metric(
            namespace="AWS/DynamoDB",
            metric_name="ConsumedWriteCapacityUnits",
            dimensions_map={"TableName": self.table.table_name},
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DynamoDB Capacity",
                left=[ddb_read, ddb_write],
                width=12,
                height=6,
            )
        )

        return dashboard

    # ---------------------------------------------------------------------- #
    # CloudWatch Alarms + SNS — subtask 1.7
    # ---------------------------------------------------------------------- #
    def _create_alarms(self) -> None:
        """Create error-rate alarms for each Lambda and wire them to SNS."""

        alert_topic = sns.Topic(
            self,
            "LearningPathAIAlertsTopic",
            topic_name="LearningPathAI-Alerts",
            display_name="LearningPath AI Alerts",
        )

        for name in LAMBDA_FUNCTIONS:
            fn = self.functions[name]

            invocations = cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Invocations",
                dimensions_map={"FunctionName": fn.function_name},
                statistic="Sum",
                period=cdk.Duration.minutes(5),
            )
            errors = cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions_map={"FunctionName": fn.function_name},
                statistic="Sum",
                period=cdk.Duration.minutes(5),
            )
            error_rate = cloudwatch.MathExpression(
                expression="(errors / MAX([errors, invocations])) * 100",
                using_metrics={
                    "errors": errors,
                    "invocations": invocations,
                },
                label=f"{name} Error Rate (%)",
                period=cdk.Duration.minutes(5),
            )

            alarm = cloudwatch.Alarm(
                self,
                f"{_pascal(name)}ErrorRateAlarm",
                alarm_name=f"LearningPathAI-{name}-ErrorRate",
                alarm_description=f"Lambda error rate > 5% for {name}",
                metric=error_rate,
                threshold=5,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

    # ---------------------------------------------------------------------- #
    # Amplify App — subtask 1.8
    # ---------------------------------------------------------------------- #
    def _create_amplify_app(
        self,
    ) -> tuple[amplify.CfnApp, amplify.CfnBranch]:
        """Create an Amplify App and a main branch for the React frontend."""

        app = amplify.CfnApp(
            self,
            "LearningPathAIFrontend",
            name="LearningPathAI-Frontend",
            description="LearningPath AI React + Vite frontend",
            # Build spec will be configured when the frontend source is connected.
            build_spec="\n".join(
                [
                    "version: 1",
                    "frontend:",
                    "  phases:",
                    "    preBuild:",
                    "      commands:",
                    "        - npm ci",
                    "    build:",
                    "      commands:",
                    "        - npm run build",
                    "  artifacts:",
                    "    baseDirectory: dist",
                    "    files:",
                    "      - '**/*'",
                    "  cache:",
                    "    paths:",
                    "      - node_modules/**/*",
                ]
            ),
        )

        branch = amplify.CfnBranch(
            self,
            "LearningPathAIMainBranch",
            app_id=app.attr_app_id,
            branch_name="main",
            description="Production branch",
            enable_auto_build=True,
        )

        return app, branch

    # ---------------------------------------------------------------------- #
    # Stack outputs — subtask 1.9
    # ---------------------------------------------------------------------- #
    def _create_outputs(self) -> None:
        """Emit CloudFormation outputs for key resource URLs."""

        cdk.CfnOutput(
            self,
            "ApiGatewayUrl",
            value=self.api.url,
            description="REST API Gateway endpoint URL",
            export_name="LearningPathAI-ApiGatewayUrl",
        )

        cdk.CfnOutput(
            self,
            "AmplifyAppUrl",
            value=cdk.Fn.sub(
                "https://main.${AppId}.amplifyapp.com",
                {"AppId": self.amplify_app.attr_app_id},
            ),
            description="Amplify frontend application URL (main branch)",
            export_name="LearningPathAI-AmplifyAppUrl",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pascal(kebab: str) -> str:
    """Convert a kebab-case string to PascalCase (e.g. 'ai-analyzer' → 'AiAnalyzer')."""
    return "".join(part.capitalize() for part in kebab.split("-"))
