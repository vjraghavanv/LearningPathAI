# Design Document: LearningPath AI

## Overview

LearningPath AI is a full-stack, AI-powered learning productivity application that eliminates decision fatigue for learners by intelligently prioritizing resources, generating personalized roadmaps, and recommending the next best learning activity based on career goals, available study time, and current progress.

The system follows a serverless AWS-native architecture:

- **Frontend**: React + Vite, hosted on AWS Amplify
- **Backend**: Python Lambda functions exposed via API Gateway
- **Persistence**: Single-table Amazon DynamoDB design
- **AI**: Amazon Bedrock Nova Lite for resource analysis and plan generation
- **Infrastructure**: AWS CDK (Python) for all provisioning
- **Observability**: Structured CloudWatch logging with dashboards and alarms

The design prioritizes low operational overhead, cost efficiency (on-demand pricing throughout), and correctness of AI-driven outputs via round-trip serialization guarantees.

---

## Architecture

```mermaid
graph TD
    User["User (Browser)"]
    Amplify["AWS Amplify\n(React + Vite)"]
    APIGW["API Gateway\n(REST + WAF + Usage Plans)"]
    Auth["Cognito / Auth\n(JWT)"]

    subgraph Lambda Functions
        RM["ResourceManager\n/resources"]
        AI_A["AI_Analyzer\n/analyze"]
        CGM["CareerGoalManager\n/career-goal"]
        AI_P["AI_Planner\n/learning-plan"]
        DB_API["DashboardAPI\n/dashboard"]
        PT["ProgressTracker\n/progress"]
        SS["SearchService\n/search"]
    end

    Bedrock["Amazon Bedrock\n(Nova Lite)"]
    DynamoDB["Amazon DynamoDB\n(Single Table)"]
    CW["CloudWatch\n(Logs + Metrics + Alarms)"]
    SNS["SNS Topic\n(Alerts)"]

    User --> Amplify
    Amplify --> APIGW
    APIGW --> Auth
    APIGW --> RM
    APIGW --> AI_A
    APIGW --> CGM
    APIGW --> AI_P
    APIGW --> DB_API
    APIGW --> PT
    APIGW --> SS

    RM --> DynamoDB
    AI_A --> Bedrock
    AI_A --> DynamoDB
    CGM --> DynamoDB
    CGM --> AI_P
    AI_P --> Bedrock
    AI_P --> DynamoDB
    DB_API --> DynamoDB
    PT --> DynamoDB
    PT --> AI_P
    SS --> DynamoDB

    Lambda Functions --> CW
    CW --> SNS
```

### Request Flow

1. The browser loads the React SPA from Amplify.
2. All API calls carry a JWT Authorization header validated at API Gateway.
3. API Gateway routes requests to the appropriate Lambda function and enforces rate limits via usage plans.
4. Lambda functions read/write DynamoDB and, where needed, invoke Bedrock.
5. Structured JSON logs from every Lambda invocation flow to CloudWatch.
6. A CloudWatch alarm fires to SNS when Lambda error rate exceeds 5% over 5 minutes.

---

## Components and Interfaces

### ResourceManager

Handles CRUD for learning resources.

| Operation | HTTP Method | Path | Notes |
|-----------|-------------|------|-------|
| Create | POST | /resources | Validates required fields; triggers AI_Analyzer |
| List | GET | /resources | Returns all resources for the authenticated userId |
| Update | PUT | /resources/{id} | Ownership check (403 if mismatch) |
| Delete | DELETE | /resources/{id} | Ownership check (403 if mismatch) |

Validation rules:
- Required fields: `title`, `url`, `resourceType`
- `resourceType` must be one of: `Technical Article`, `Documentation`, `YouTube Video`, `Online Course`, `PDF`, `GitHub Repository`
- `difficulty` (optional at creation) must be one of: `Beginner`, `Intermediate`, `Advanced`

### AI_Analyzer

Invoked after a resource is persisted. Calls Bedrock Nova Lite with a structured prompt requesting JSON output. Merges AI metadata back into the DynamoDB record. On error, retains the original record with AI fields set to null and logs to CloudWatch. Must complete within 30 seconds.

**Bedrock prompt contract** (fields requested in prompt):
```json
{
  "priorityScore": 0,
  "summary": "",
  "skills": [],
  "difficulty": "",
  "estimatedTime": "",
  "whyLearnNow": "",
  "recommendedWeek": 0
}
```

### CareerGoalManager

Persists and validates user career goal profiles.

| Field | Type | Constraints |
|-------|------|-------------|
| careerGoal | string | Predefined option or free-text ≤ 200 chars |
| currentSkillLevel | enum | Beginner, Intermediate, Advanced |
| weeklyStudyHours | integer | 1–168 |
| targetCompletionDate | date | ISO 8601, optional |
| preferredLearningPace | enum | Slow, Moderate, Fast |

On successful update, triggers AI_Planner to regenerate the Learning_Plan.

### AI_Planner

Generates personalized Learning_Plans by calling Bedrock Nova Lite. Must complete within 60 seconds. Persists the result to DynamoDB. On error, returns HTTP 503 and preserves the last valid plan.

**Bedrock prompt contract** (Learning_Plan output):
```json
{
  "dailySchedule": [
    {
      "day": 1,
      "resourceId": "",
      "estimatedDuration": "",
      "recommendationReason": ""
    }
  ],
  "weeklyRoadmap": [],
  "recommendedProjects": [],
  "certificationRecommendations": [],
  "estimatedCompletionTimeline": ""
}
```

### DashboardAPI

Aggregates data from DynamoDB into a single response on GET /dashboard. Computes:
- Today's task (resource scheduled for current date in active plan)
- Completion percentage (completed / non-skipped resources, rounded to 1 decimal)
- Study streak (consecutive days with at least one completion)
- Weekly progress, roadmap, priority resources, certifications, projects

Must respond within 3 seconds. Returns null plan-dependent fields when no active plan exists.

### ProgressTracker

Handles PATCH/PUT /progress/{id}. Persists new Learning_Status, records completion timestamp if status is `Completed`, increments streak, triggers AI_Planner regeneration on completion, and records milestone events at 25/50/75/100% thresholds.

### SearchService

Handles filtered resource queries. Supports AND-logic across: `technology`, `difficulty`, `resourceType`, `certificationTag`, `skillTag`, `tag` (free-text). Returns empty list (HTTP 200) on no results. Returns HTTP 400 for unrecognized filter keys. Must respond within 2 seconds.

### Pretty Printer

A shared utility module that serializes DynamoDB resource records and Learning_Plan objects back into the exact JSON structure expected by Bedrock prompts. Used to support round-trip correctness: re-analyzing or re-planning with the same data must produce an equivalent result.

---

## Data Models

### DynamoDB Single-Table Design

**Table name**: `LearningPathAI`
**Partition key**: `userId` (String)
**Sort key**: `resourceId` (String)

Special sort key prefixes distinguish record types:

| Record Type | Sort Key Format | Description |
|-------------|----------------|-------------|
| Resource | `RESOURCE#<uuid>` | Individual learning resource |
| Career Goal | `PROFILE#career_goal` | User's career goal profile |
| Learning Plan | `PLAN#active` | Current active learning plan |
| Progress Event | `PROGRESS#<resourceId>#<timestamp>` | Status change audit entry |
| Milestone | `MILESTONE#<threshold>` | Milestone event record |
| Streak | `STREAK#current` | Current streak metadata |

### Resource Item Schema

```json
{
  "userId": "string",
  "resourceId": "RESOURCE#<uuid>",
  "title": "string",
  "url": "string",
  "resourceType": "Technical Article | Documentation | YouTube Video | Online Course | PDF | GitHub Repository",
  "estimatedDuration": "string",
  "difficulty": "Beginner | Intermediate | Advanced",
  "tags": ["string"],
  "technology": "string",
  "learningStatus": "Not Started | In Progress | Completed | Skipped",
  "completionTimestamp": "ISO8601 | null",
  "completionPercentage": "number",
  "aiMetadata": {
    "priorityScore": "number (0-100)",
    "summary": "string",
    "skills": ["string"],
    "difficulty": "string",
    "estimatedTime": "string",
    "whyLearnNow": "string",
    "recommendedWeek": "number"
  },
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601"
}
```

### Career Goal Profile Schema

```json
{
  "userId": "string",
  "resourceId": "PROFILE#career_goal",
  "careerGoal": "string",
  "currentSkillLevel": "Beginner | Intermediate | Advanced",
  "weeklyStudyHours": "integer (1-168)",
  "targetCompletionDate": "ISO8601 | null",
  "preferredLearningPace": "Slow | Moderate | Fast",
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601"
}
```

### Learning Plan Schema

```json
{
  "userId": "string",
  "resourceId": "PLAN#active",
  "dailySchedule": [
    {
      "day": "integer",
      "date": "ISO8601",
      "resourceId": "string",
      "estimatedDuration": "string",
      "recommendationReason": "string"
    }
  ],
  "weeklyRoadmap": ["string"],
  "recommendedProjects": ["string"],
  "certificationRecommendations": ["string"],
  "estimatedCompletionTimeline": "string",
  "generatedAt": "ISO8601",
  "careerGoalSnapshot": {}
}
```

### Milestone Schema

```json
{
  "userId": "string",
  "resourceId": "MILESTONE#<threshold>",
  "threshold": "number (25 | 50 | 75 | 100)",
  "recordedAt": "ISO8601"
}
```

### Streak Schema

```json
{
  "userId": "string",
  "resourceId": "STREAK#current",
  "currentStreak": "integer",
  "lastCompletionDate": "ISO8601 | null"
}
```

---


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Resource persistence round-trip

*For any* valid resource payload submitted by a user, persisting it and then retrieving the resource list for that userId should return a record containing all the submitted field values.

**Validates: Requirements 1.1, 1.2**

---

### Property 2: Resource update round-trip

*For any* existing resource and any valid update payload, after applying the update, the retrieved resource should reflect all the new field values.

**Validates: Requirements 1.3**

---

### Property 3: Resource deletion removes from list

*For any* resource that exists for a userId, after a successful delete, listing resources for that userId should not include that resourceId.

**Validates: Requirements 1.4**

---

### Property 4: Resource input validation rejects invalid fields

*For any* resource payload missing one of the required fields (`title`, `url`, `resourceType`), or supplying an invalid `resourceType` or `difficulty` value, the Resource_Manager should reject the request with HTTP 400.

**Validates: Requirements 1.5, 1.7, 1.8**

---

### Property 5: Ownership enforcement returns 403

*For any* resource owned by userId A, a mutating request (update, delete, or status change) from a different userId B should be rejected with HTTP 403.

**Validates: Requirements 1.6, 6.7**

---

### Property 6: AI metadata fields are populated after analysis

*For any* resource for which Bedrock returns a valid JSON response, the merged DynamoDB record should contain non-null values for all required AI metadata fields: `priorityScore`, `summary`, `skills`, `difficulty`, `estimatedTime`, `whyLearnNow`, `recommendedWeek`.

**Validates: Requirements 2.2, 2.4**

---

### Property 7: AI metadata prompt always contains required keys

*For any* resource input, the prompt construction function should always produce a JSON template containing all required Bedrock response keys.

**Validates: Requirements 2.3**

---

### Property 8: Bedrock error preserves original resource record

*For any* Bedrock error or non-JSON response during analysis, the resource record should still exist in DynamoDB with original user-supplied fields intact, and all AI metadata fields should be null.

**Validates: Requirements 2.5**

---

### Property 9: AI metadata serialization round-trip

*For any* resource record containing AI metadata, serializing it through the Pretty_Printer and then parsing the output should produce a JSON object equivalent to the original AI metadata structure.

**Validates: Requirements 2.7**

---

### Property 10: Career goal profile persistence round-trip

*For any* valid career goal profile, persisting it and then retrieving it should return a record with all the submitted field values.

**Validates: Requirements 3.1, 3.2**

---

### Property 11: Career goal field validation

*For any* career goal profile where `weeklyStudyHours` is outside [1, 168], or `currentSkillLevel` or `preferredLearningPace` is not in the accepted enum set, or a required field is missing, the Career_Goal_Manager should reject the request with HTTP 400.

**Validates: Requirements 3.3, 3.4, 3.5, 3.6, 3.7**

---

### Property 12: Learning_Plan structural invariants

*For any* generated Learning_Plan, the daily schedule must contain at least 7 entries, and each entry must include `resourceId`, `estimatedDuration`, and `recommendationReason`. Additionally, all `priorityScore` values in the plan must be in the range [0, 100].

**Validates: Requirements 4.3, 4.6**

---

### Property 13: Learning_Plan respects daily study budget

*For any* generated Learning_Plan and the user profile used to create it, no single day's total scheduled study time should exceed the user's average daily availability (weeklyStudyHours / 7).

**Validates: Requirements 4.5**

---

### Property 14: Completed and Skipped resources are excluded from plans

*For any* user who has resources with Learning_Status `Completed` or `Skipped`, no generated or regenerated Learning_Plan should schedule any of those resources on any day.

**Validates: Requirements 4.7, 7.1, 7.3**

---

### Property 15: Learning_Plan serialization round-trip

*For any* Learning_Plan object, serializing it through the Pretty_Printer and then parsing the output should produce a JSON object structurally equivalent to the original plan.

**Validates: Requirements 4.10**

---

### Property 16: Dashboard response completeness

*For any* user with an active Learning_Plan and at least one resource, the dashboard response should contain non-null values for all required aggregated fields: today's task, completion percentage, study streak, weekly progress, roadmap, priority resources, certifications, and projects.

**Validates: Requirements 5.1**

---

### Property 17: Completion percentage arithmetic

*For any* collection of user resources with assigned statuses, the computed `completionPercentage` should equal `(count of Completed) / (count of non-Skipped) * 100`, rounded to 1 decimal place.

**Validates: Requirements 5.4**

---

### Property 18: Study streak computation

*For any* sequence of completion timestamps, the computed study streak should equal the number of consecutive calendar days (ending with today) on which at least one completion occurred.

**Validates: Requirements 5.3, 6.4, 6.5**

---

### Property 19: Progress status update persistence

*For any* valid Learning_Status value submitted for a resource, after the update, retrieving that resource should reflect the new status.

**Validates: Requirements 6.1, 6.2**

---

### Property 20: Milestone events are recorded at thresholds

*For any* sequence of resource completions that causes the overall completion percentage to cross a threshold (25, 50, 75, or 100), a Milestone record for that threshold should exist in DynamoDB with a timestamp.

**Validates: Requirements 6.6**

---

### Property 21: Plan preserved on regeneration failure

*For any* regeneration attempt that fails (Bedrock error or timeout), the DynamoDB record for the active Learning_Plan should remain unchanged from its last successfully generated state.

**Validates: Requirements 7.5**

---

### Property 22: Search returns all matching resources with AND logic

*For any* set of resources belonging to a userId and any combination of valid filter parameters, the search results should include every resource that satisfies all supplied filters, and no resource that fails any filter.

**Validates: Requirements 8.1, 8.3**

---

### Property 23: Search with unrecognized filter key returns HTTP 400

*For any* search request containing a filter key not in the supported set, the Search_Service should return HTTP 400.

**Validates: Requirements 8.6**

---

### Property 24: All endpoints require valid authorization

*For any* API endpoint and any request without a valid Authorization header, the response should be HTTP 401.

**Validates: Requirements 9.2**

---

### Property 25: Unhandled exceptions do not expose stack traces

*For any* Lambda function invocation that results in an unhandled exception, the API response should be HTTP 500 with a generic error message and should not contain stack trace details, file paths, or internal exception messages.

**Validates: Requirements 9.5**

---

### Property 26: Structured log entries contain required fields

*For any* Lambda invocation (successful or error), the emitted CloudWatch log entry should be valid JSON containing at minimum: `userId` (if available), `path`, `statusCode`, `durationMs`, and `correlationId`. For error invocations, the log should additionally contain `errorType` and a sanitized `errorMessage`.

**Validates: Requirements 12.1, 12.2**

---

## Error Handling

### Validation Errors (HTTP 400)

All input validation errors return HTTP 400 with a JSON body:
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Descriptive message identifying the specific issue",
  "field": "fieldName (if applicable)"
}
```

### Authorization Errors (HTTP 401 / 403)

- HTTP 401: Missing or invalid Authorization header (enforced at API Gateway level)
- HTTP 403: Valid user but attempting to access another user's resource (enforced in Lambda)

### AI Service Errors

- Bedrock analysis failure: Resource record is retained with null AI fields; error logged to CloudWatch. No error surfaced to the user during async analysis.
- Bedrock plan generation failure: HTTP 503 returned with message "Plan generation temporarily unavailable"; last valid plan preserved.

### Rate Limiting (HTTP 429)

Enforced at API Gateway with usage plans. Response body:
```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Too many requests. Limit: 100 requests per minute."
}
```

### Unsupported Media Type (HTTP 415)

Returned when POST/PUT requests have non-`application/json` Content-Type.

### Internal Server Error (HTTP 500)

All unhandled Lambda exceptions are caught by a top-level error handler that returns HTTP 500 with a generic message. Stack traces are never forwarded to the caller.

### DynamoDB Transient Errors

Lambda functions use exponential backoff with up to 3 retries for DynamoDB throttling errors before returning HTTP 503.

---

## Testing Strategy

### Dual Testing Approach

Both unit tests and property-based tests are required. They are complementary:

- **Unit tests** verify specific examples, integration points, edge cases, and error conditions
- **Property tests** verify universal properties across all possible inputs using randomized generation

### Property-Based Testing

**Library**: [Hypothesis](https://hypothesis.readthedocs.io/) for Python backend; [fast-check](https://github.com/dubzzz/fast-check) for React frontend.

Each correctness property listed above must be implemented as a single property-based test with a minimum of **100 iterations**.

Every property test must include a comment referencing the design property:
```python
# Feature: learningpath-ai, Property 1: Resource persistence round-trip
```

Tag format: `Feature: learningpath-ai, Property {number}: {property_text}`

### Unit Testing

Unit tests focus on:
- Specific valid and invalid example inputs for each API endpoint
- Edge cases: empty resource list, no active plan, zero study streak, completion percentage of exactly 0% and 100%
- Integration points between Lambda functions (e.g., ProgressTracker triggering AI_Planner)
- Error conditions: Bedrock timeout, DynamoDB throttle, malformed JSON from Bedrock

Avoid over-testing with unit tests where property tests already provide comprehensive coverage.

### Backend Test Structure

```
tests/
  unit/
    test_resource_manager.py
    test_ai_analyzer.py
    test_career_goal_manager.py
    test_ai_planner.py
    test_dashboard_api.py
    test_progress_tracker.py
    test_search_service.py
    test_pretty_printer.py
  property/
    test_resource_properties.py      # Properties 1-5
    test_ai_analyzer_properties.py   # Properties 6-9
    test_career_goal_properties.py   # Properties 10-11
    test_ai_planner_properties.py    # Properties 12-15
    test_dashboard_properties.py     # Properties 16-18
    test_progress_properties.py      # Properties 19-21
    test_search_properties.py        # Properties 22-23
    test_api_properties.py           # Properties 24-26
```

### Frontend Test Structure

```
src/__tests__/
  unit/
    Dashboard.test.tsx
    ResourceManager.test.tsx
    ProgressTracker.test.tsx
  property/
    dashboard.property.test.ts       # Properties 16-18
    search.property.test.ts          # Property 22
```

### Infrastructure Testing

- CDK stack synthesizes without error (`cdk synth`)
- All Lambda IAM policies validated for least-privilege using `cfn-lint` or CDK assertions
- DynamoDB table configured with on-demand capacity and PITR enabled (CDK assertion tests)

### End-to-End Testing

A minimal set of Playwright tests covers the happy path:
1. User sets career goal → plan is generated → dashboard shows today's task
2. User marks a resource complete → streak increments → plan regenerates
3. User searches resources with filters → correct results returned
