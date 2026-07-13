# Tasks

## Task List

- [x] 1 Project Scaffolding and Infrastructure Foundation
  - [x] 1.1 Initialize AWS CDK Python project structure with app entry point, stack file, and requirements.txt
  - [x] 1.2 Define DynamoDB single-table construct with on-demand capacity, PITR enabled, and deletion protection flag for production
  - [x] 1.3 Define IAM roles with least-privilege policies for each Lambda function
  - [x] 1.4 Define API Gateway REST API construct with AWS WAF integration, usage plans, and per-user rate limit of 100 req/min
  - [x] 1.5 Define CloudWatch log groups with 30-day retention for all Lambda functions
  - [x] 1.6 Define CloudWatch Dashboard with Lambda invocation count, error rate, P95 duration, API Gateway 4xx/5xx rates, and DynamoDB consumed capacity metrics
  - [x] 1.7 Define CloudWatch Alarm for Lambda error rate > 5% over 5-minute window publishing to SNS topic
  - [x] 1.8 Define Amplify App construct for React frontend hosting
  - [x] 1.9 Add CDK stack outputs for API Gateway endpoint URL and Amplify App URL
  - [x] 1.10 Verify `cdk synth` executes without errors

- [x] 2 Backend Shared Utilities
  - [x] 2.1 Implement structured JSON logger utility emitting userId, path, statusCode, durationMs, and correlationId on every invocation
  - [x] 2.2 Implement top-level Lambda error handler that catches unhandled exceptions and returns HTTP 500 without stack traces
  - [x] 2.3 Implement DynamoDB client wrapper with exponential backoff retry (up to 3 retries) for throttling errors
  - [x] 2.4 Implement correlation ID propagation utility (extracted from API Gateway context, forwarded to Bedrock and DynamoDB calls)
  - [x] 2.5 Implement Pretty_Printer module that serializes resource AI metadata into the Bedrock prompt JSON structure
  - [x] 2.6 Implement Pretty_Printer module that serializes Learning_Plan objects into the Bedrock prompt JSON structure
  - [x] 2.7 Write property tests for Pretty_Printer AI metadata round-trip (Property 9)
  - [x] 2.8 Write property tests for Pretty_Printer Learning_Plan round-trip (Property 15)

- [x] 3 Resource Manager Lambda
  - [x] 3.1 Implement POST /resources handler: validate required fields (title, url, resourceType), persist to DynamoDB, trigger AI_Analyzer
  - [x] 3.2 Implement GET /resources handler: query DynamoDB for all resources by userId
  - [x] 3.3 Implement PUT /resources/{id} handler: ownership check (403), overwrite metadata fields, return updated resource
  - [x] 3.4 Implement DELETE /resources/{id} handler: ownership check (403), remove item from DynamoDB
  - [x] 3.5 Implement input validation: resourceType enum check, difficulty enum check, HTTP 400 with descriptive message for missing/invalid fields
  - [x] 3.6 Wire ResourceManager Lambda into CDK stack with DynamoDB table name and environment variable
  - [x] 3.7 Write property tests for resource persistence round-trip (Property 1)
  - [x] 3.8 Write property tests for resource update round-trip (Property 2)
  - [x] 3.9 Write property tests for resource deletion removes from list (Property 3)
  - [x] 3.10 Write property tests for resource input validation rejects invalid fields (Property 4)
  - [x] 3.11 Write property tests for ownership enforcement returns 403 (Property 5)

- [x] 4 AI Analyzer Lambda
  - [x] 4.1 Implement /analyze handler: accept resourceId, fetch resource from DynamoDB, build Bedrock Nova Lite prompt requesting JSON with all required fields
  - [x] 4.2 Implement Bedrock invocation with 30-second timeout; on success merge AI metadata into DynamoDB resource record
  - [x] 4.3 Implement error handling: on Bedrock error or non-JSON response, log to CloudWatch at ERROR level and retain resource with AI fields null
  - [x] 4.4 Wire AI_Analyzer Lambda into CDK stack with DynamoDB table name and Bedrock model ID environment variables
  - [x] 4.5 Write property tests for AI metadata fields populated after analysis (Property 6)
  - [x] 4.6 Write property tests for AI metadata prompt always contains required keys (Property 7)
  - [x] 4.7 Write property tests for Bedrock error preserves original resource record (Property 8)

- [x] 5 Career Goal Manager Lambda
  - [x] 5.1 Implement POST /career-goal handler: validate required fields (careerGoal, currentSkillLevel, weeklyStudyHours), persist profile to DynamoDB
  - [x] 5.2 Implement PUT /career-goal handler: overwrite updated fields, return complete profile, trigger AI_Planner regeneration
  - [x] 5.3 Implement field validation: careerGoal free-text ≤ 200 chars, currentSkillLevel enum, weeklyStudyHours integer 1–168, preferredLearningPace enum; return HTTP 400 on failure
  - [x] 5.4 Wire CareerGoalManager Lambda into CDK stack
  - [x] 5.5 Write property tests for career goal profile persistence round-trip (Property 10)
  - [x] 5.6 Write property tests for career goal field validation (Property 11)

- [x] 6 AI Planner Lambda
  - [x] 6.1 Implement POST /learning-plan handler: fetch career goal profile and resource list for userId, build Bedrock prompt, invoke Nova Lite with 60-second timeout
  - [x] 6.2 Implement Learning_Plan parsing: parse Bedrock JSON response into structured Learning_Plan object with daily schedule (≥7 days), weekly roadmap, projects, certifications, timeline
  - [x] 6.3 Implement scheduling constraint: validate that no single day's assigned study time exceeds average daily availability (weeklyStudyHours / 7)
  - [x] 6.4 Implement resource exclusion: filter out resources with Learning_Status Completed or Skipped before building prompt
  - [x] 6.5 Implement Priority_Score assignment: validate all scores are in [0, 100] range
  - [x] 6.6 Implement error handling: on Bedrock error return HTTP 503, preserve last valid plan in DynamoDB, log to CloudWatch
  - [x] 6.7 Persist generated Learning_Plan to DynamoDB under PLAN#active sort key
  - [x] 6.8 Wire AI_Planner Lambda into CDK stack with DynamoDB table name and Bedrock model ID environment variables
  - [x] 6.9 Write property tests for Learning_Plan structural invariants (Property 12)
  - [x] 6.10 Write property tests for Learning_Plan respects daily study budget (Property 13)
  - [x] 6.11 Write property tests for Completed and Skipped resources excluded from plans (Property 14)
  - [x] 6.12 Write property tests for plan preserved on regeneration failure (Property 21)

- [x] 7 Dashboard API Lambda
  - [x] 7.1 Implement GET /dashboard handler: fetch active Learning_Plan, all resources, and streak record from DynamoDB in parallel
  - [x] 7.2 Implement today's task computation: select resource scheduled for current calendar date from active plan
  - [x] 7.3 Implement completion percentage computation: (count Completed) / (count non-Skipped) * 100, rounded to 1 decimal
  - [x] 7.4 Implement study streak computation: count consecutive calendar days ending today with at least one completion
  - [x] 7.5 Implement no-plan fallback: return null for plan-dependent fields with a prompt message when no active plan exists
  - [x] 7.6 Wire DashboardAPI Lambda into CDK stack; ensure response time target of 3 seconds is met via parallel DynamoDB fetches
  - [x] 7.7 Write property tests for dashboard response completeness (Property 16)
  - [x] 7.8 Write property tests for completion percentage arithmetic (Property 17)
  - [x] 7.9 Write property tests for study streak computation (Property 18)
  - [x] 7.10 Write unit test for no-plan edge case (Property 16 edge case)

- [x] 8 Progress Tracker Lambda
  - [x] 8.1 Implement PUT /progress/{id} handler: ownership check (403), validate Learning_Status enum, persist new status to DynamoDB
  - [x] 8.2 On Completed status: record completion timestamp, trigger AI_Planner regeneration
  - [x] 8.3 Implement streak increment: when a resource is completed on a new calendar day, increment STREAK#current by 1
  - [x] 8.4 Implement streak reset: a scheduled CloudWatch Event at midnight UTC checks if lastCompletionDate is not today and resets streak to 0
  - [x] 8.5 Implement milestone recording: when completion percentage crosses 25/50/75/100%, write a MILESTONE#<threshold> record with timestamp
  - [x] 8.6 Wire ProgressTracker Lambda and streak-reset scheduled rule into CDK stack
  - [x] 8.7 Write property tests for progress status update persistence (Property 19)
  - [x] 8.8 Write property tests for study streak increment and reset (Property 18 — shared with Dashboard)
  - [x] 8.9 Write property tests for milestone events recorded at thresholds (Property 20)

- [x] 9 Search Service Lambda
  - [x] 9.1 Implement GET /search handler: parse and validate filter parameters (technology, difficulty, resourceType, certificationTag, skillTag, tag); return HTTP 400 for unrecognized keys
  - [x] 9.2 Implement AND-logic filter evaluation: return only resources satisfying all supplied filters for the authenticated userId
  - [x] 9.3 Return empty list with HTTP 200 when no resources match
  - [x] 9.4 Wire SearchService Lambda into CDK stack; validate response time target of 2 seconds
  - [x] 9.5 Write property tests for search returns all matching resources with AND logic (Property 22)
  - [x] 9.6 Write property tests for unrecognized filter key returns HTTP 400 (Property 23)

- [x] 10 API Gateway Security and Cross-Cutting Concerns
  - [x] 10.1 Configure API Gateway authorizer (Cognito or Lambda authorizer) to return HTTP 401 for missing or invalid Authorization headers
  - [x] 10.2 Configure API Gateway Content-Type validation to return HTTP 415 for non-application/json POST/PUT requests
  - [x] 10.3 Configure API Gateway to return HTTP 500 with generic message for unhandled Lambda exceptions (without stack traces)
  - [x] 10.4 Write property tests for all endpoints require valid authorization (Property 24)
  - [x] 10.5 Write property tests for unhandled exceptions do not expose stack traces (Property 25)
  - [x] 10.6 Write property tests for structured log entries contain required fields (Property 26)

- [x] 11 React Frontend — Core Setup
  - [x] 11.1 Initialize React + Vite project with TypeScript, configure Amplify hosting connection
  - [x] 11.2 Implement dark/light mode toggle persisting preference to localStorage; apply system `prefers-color-scheme` on first load if no preference stored
  - [x] 11.3 Implement responsive layout with sidebar navigation and main content area (375px / 768px / 1280px breakpoints)
  - [x] 11.4 Implement global API client with Authorization header injection, loading state management, and user-readable error display
  - [x] 11.5 Implement onboarding prompt displayed when no active Learning_Plan exists

- [x] 12 React Frontend — Dashboard View
  - [x] 12.1 Implement Today's Task card component
  - [x] 12.2 Implement progress charts (completion percentage, weekly progress)
  - [x] 12.3 Implement learning timeline / roadmap component
  - [x] 12.4 Implement study streak display
  - [x] 12.5 Implement priority resources and certification recommendations sections
  - [x] 12.6 Implement dashboard optimistic update: after Learning_Status change, update dashboard view without full page reload

- [x] 13 React Frontend — Resource Management View
  - [x] 13.1 Implement resource list view with status indicators
  - [x] 13.2 Implement add resource form with all fields and client-side validation
  - [x] 13.3 Implement edit and delete resource actions
  - [x] 13.4 Implement search and filter UI wired to Search Service

- [x] 14 React Frontend — Career Goal and Plan Views
  - [x] 14.1 Implement career goal setup form with all required fields
  - [x] 14.2 Implement learning plan view showing daily schedule with recommendation reasons

- [x] 15 End-to-End and Integration Verification
  - [x] 15.1 Write Playwright E2E test: user sets career goal → plan generated → dashboard shows today's task
  - [x] 15.2 Write Playwright E2E test: user marks resource complete → streak increments → plan regenerates
  - [x] 15.3 Write Playwright E2E test: user searches resources with multiple filters → correct results returned
  - [x] 15.4 Run `cdk synth` and validate all CDK assertion tests for DynamoDB config (on-demand, PITR, deletion protection)
  - [x] 15.5 Run full backend test suite (unit + property) and confirm all property tests execute with ≥ 100 iterations
