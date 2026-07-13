# Requirements Document

## Introduction

LearningPath AI is a production-ready, full-stack AI-powered learning productivity application. It eliminates decision fatigue for learners by intelligently prioritizing learning resources, generating personalized learning roadmaps, and recommending the next best learning activity based on career goals, available study time, and current progress. The application acts as a personal AI learning mentor rather than a traditional learning management system.

Target users include students, developers, cloud engineers, DevOps engineers, QA engineers, and professionals preparing for certifications.

The system is built on a React + Vite frontend hosted on AWS Amplify, a Python backend running on AWS Lambda behind API Gateway, Amazon DynamoDB for persistence, Amazon Bedrock (Nova Lite) for AI capabilities, and AWS CDK for infrastructure-as-code.

---

## Glossary

- **LearningPath_AI**: The full-stack application described in this document.
- **Resource**: A learning item added by a user, including articles, videos, courses, PDFs, documentation, or GitHub repositories.
- **Resource_Type**: One of: Technical Article, Documentation, YouTube Video, Online Course, PDF, GitHub Repository.
- **Career_Goal**: A user-defined target professional outcome (e.g., "Become AWS Cloud Engineer", "Crack AWS SAA Certification").
- **Learning_Plan**: An AI-generated daily and weekly schedule of resources aligned to a user's Career_Goal and available study hours.
- **Priority_Score**: A numeric value (0–100) assigned by the AI Analyzer indicating how urgently a resource should be studied given the user's current Career_Goal and progress.
- **Learning_Status**: The current state of a Resource for a given user: Not Started, In Progress, Completed, or Skipped.
- **AI_Analyzer**: The Lambda function that calls Amazon Bedrock Nova Lite to enrich a Resource with metadata.
- **AI_Planner**: The Lambda function that calls Amazon Bedrock Nova Lite to generate a personalized Learning_Plan.
- **Dashboard**: The main UI view summarizing today's task, progress metrics, roadmap, and recommendations.
- **Study_Streak**: The count of consecutive days on which a user logged at least one completed learning activity.
- **Milestone**: A system-defined achievement triggered when a user reaches a completion threshold (e.g., 25%, 50%, 75%, 100% of a Career_Goal plan).
- **Recommendation_Reason**: A natural-language explanation of why a specific Resource was recommended by the AI_Planner.
- **DynamoDB_Table**: The single Amazon DynamoDB table storing all user and resource data, keyed by userId (partition key) and resourceId (sort key).
- **API_Gateway**: The AWS API Gateway REST API that routes HTTP requests to Lambda functions.
- **CDK_Stack**: The AWS CDK Python stack that provisions all infrastructure components.
- **Amplify_App**: The AWS Amplify hosting configuration for the React frontend.
- **User**: An authenticated individual using LearningPath_AI.

---

## Requirements

### Requirement 1: Learning Resource Management

**User Story:** As a learner, I want to add, view, update, and delete learning resources, so that I can maintain a personal library of content aligned to my career goals.

#### Acceptance Criteria

1. WHEN a User submits a new Resource with a title, URL, resource type, estimated duration, difficulty, tags, and technology, THE Resource_Manager SHALL persist the Resource to the DynamoDB_Table under the User's userId.
2. WHEN a User requests the list of their Resources, THE Resource_Manager SHALL return all Resources associated with that userId from the DynamoDB_Table.
3. WHEN a User updates an existing Resource's metadata fields, THE Resource_Manager SHALL overwrite those fields in the DynamoDB_Table and return the updated Resource.
4. WHEN a User deletes a Resource by its resourceId, THE Resource_Manager SHALL remove the corresponding item from the DynamoDB_Table.
5. IF a User submits a Resource without a required field (title, URL, or resource type), THEN THE Resource_Manager SHALL return an HTTP 400 response with a descriptive error message identifying the missing field.
6. IF a User attempts to update or delete a Resource that does not belong to their userId, THEN THE Resource_Manager SHALL return an HTTP 403 response.
7. THE Resource_Manager SHALL support the following Resource_Type values: Technical Article, Documentation, YouTube Video, Online Course, PDF, GitHub Repository.
8. WHEN a User provides a difficulty value for a Resource, THE Resource_Manager SHALL accept one of: Beginner, Intermediate, Advanced.

---

### Requirement 2: AI Resource Analyzer

**User Story:** As a learner, I want newly added resources to be automatically analyzed by AI, so that I receive enriched metadata without manual effort.

#### Acceptance Criteria

1. WHEN a new Resource is persisted, THE AI_Analyzer SHALL invoke Amazon Bedrock Nova Lite with the resource title, URL, and description to generate AI metadata.
2. THE AI_Analyzer SHALL extract and store the following fields from the Bedrock response: summary, identified technologies, extracted skills, estimated learning effort, difficulty, tags, and Priority_Score.
3. THE AI_Analyzer SHALL always request a JSON-formatted response from Amazon Bedrock Nova Lite containing at minimum: `priorityScore`, `summary`, `skills`, `difficulty`, `estimatedTime`, `whyLearnNow`, and `recommendedWeek`.
4. WHEN Amazon Bedrock Nova Lite returns a valid JSON response, THE AI_Analyzer SHALL merge the AI metadata into the existing Resource record in the DynamoDB_Table.
5. IF Amazon Bedrock Nova Lite returns an error or a non-JSON response, THEN THE AI_Analyzer SHALL log the error to CloudWatch and retain the Resource record with its original user-supplied fields, setting AI metadata fields to null.
6. THE AI_Analyzer SHALL complete metadata enrichment and update the DynamoDB_Table within 30 seconds of a Resource being persisted.
7. THE Pretty_Printer SHALL format AI metadata stored in DynamoDB back into the same JSON structure accepted by the Bedrock prompt, so that re-analysis of a Resource produces an equivalent result (round-trip property).

---

### Requirement 3: Career Goal Setup

**User Story:** As a learner, I want to define my career goal, skill level, and study availability, so that the AI can generate a plan tailored to my specific situation.

#### Acceptance Criteria

1. WHEN a User submits a Career_Goal profile containing career goal, current skill level, weekly study hours, target completion date, and preferred learning pace, THE Career_Goal_Manager SHALL persist the profile to the DynamoDB_Table under the User's userId.
2. WHEN a User updates any field of their Career_Goal profile, THE Career_Goal_Manager SHALL overwrite the updated fields and return the complete updated profile.
3. THE Career_Goal_Manager SHALL accept a career goal from the following options: Become AWS Cloud Engineer, Become DevOps Engineer, Become AI Engineer, Crack AWS SAA Certification, Become Playwright Automation Expert, or a free-text string up to 200 characters.
4. THE Career_Goal_Manager SHALL accept current skill level as one of: Beginner, Intermediate, Advanced.
5. THE Career_Goal_Manager SHALL accept weekly study hours as a positive integer between 1 and 168.
6. THE Career_Goal_Manager SHALL accept preferred learning pace as one of: Slow, Moderate, Fast.
7. IF a User submits a Career_Goal profile missing the career goal, current skill level, or weekly study hours, THEN THE Career_Goal_Manager SHALL return an HTTP 400 response with a descriptive error message.
8. WHEN a User's Career_Goal profile is updated, THE AI_Planner SHALL be triggered to regenerate the User's Learning_Plan using the new profile data.

---

### Requirement 4: AI Learning Planner

**User Story:** As a learner, I want the AI to generate a daily and weekly learning roadmap aligned to my career goal and available study hours, so that I always know exactly what to learn today and why.

#### Acceptance Criteria

1. WHEN the AI_Planner is triggered, THE AI_Planner SHALL invoke Amazon Bedrock Nova Lite with the User's Career_Goal profile and their list of Resources to generate a Learning_Plan.
2. THE AI_Planner SHALL always request a JSON-formatted response from Amazon Bedrock Nova Lite and SHALL parse the response into a structured Learning_Plan object.
3. THE Learning_Plan SHALL contain a daily schedule for at least 7 days, where each day specifies the assigned Resource, estimated study duration, and a Recommendation_Reason explaining why that Resource was selected for that day.
4. THE Learning_Plan SHALL include a weekly roadmap, a list of recommended projects, certification recommendations, and an estimated completion timeline for the Career_Goal.
5. WHEN the AI_Planner assigns Resources to days, THE AI_Planner SHALL respect the User's weekly study hours and SHALL NOT schedule more daily study time than the User's average daily availability allows.
6. WHEN the AI_Planner generates a Learning_Plan, THE AI_Planner SHALL assign a Priority_Score (0–100) to each Resource based on its relevance to the User's Career_Goal and current Learning_Status.
7. WHEN the AI_Planner generates recommendations, THE AI_Planner SHALL exclude Resources whose Learning_Status is Completed or Skipped.
8. IF Amazon Bedrock Nova Lite returns an error during plan generation, THEN THE AI_Planner SHALL log the error to CloudWatch and return an HTTP 503 response with a message indicating that plan generation is temporarily unavailable.
9. THE AI_Planner SHALL complete Learning_Plan generation and persist the result to the DynamoDB_Table within 60 seconds of being triggered.
10. THE Pretty_Printer SHALL format a Learning_Plan object back into the JSON structure accepted by the Bedrock prompt, so that re-planning with the same inputs produces an equivalent plan (round-trip property).

---

### Requirement 5: Dashboard

**User Story:** As a learner, I want a single dashboard view that shows my today's task, progress metrics, roadmap, and recommendations, so that I can get oriented and start learning without navigating multiple screens.

#### Acceptance Criteria

1. WHEN a User loads the Dashboard, THE Dashboard_API SHALL return a single aggregated response containing: today's learning task, current completion percentage, weekly progress, Study_Streak, full Learning_Plan roadmap, priority Resources, upcoming certification recommendations, and recommended projects.
2. THE Dashboard_API SHALL compute the today's learning task by selecting the Resource scheduled for the current calendar day in the active Learning_Plan.
3. THE Dashboard_API SHALL compute the Study_Streak as the number of consecutive prior calendar days on which the User completed at least one Resource, including the current day if a Resource has already been completed today.
4. THE Dashboard_API SHALL compute the current completion percentage as the count of Resources with Learning_Status Completed divided by the total count of non-Skipped Resources for the User, expressed as a percentage rounded to one decimal place.
5. THE Dashboard_API SHALL respond within 3 seconds under normal load conditions.
6. IF a User has no active Learning_Plan, THEN THE Dashboard_API SHALL return a response with null values for plan-dependent fields and a message prompting the User to set up a Career_Goal.

---

### Requirement 6: Progress Tracking

**User Story:** As a learner, I want to update the status of each resource and have my progress metrics automatically updated, so that the AI always recommends what is next rather than what I have already done.

#### Acceptance Criteria

1. WHEN a User updates the Learning_Status of a Resource, THE Progress_Tracker SHALL persist the new Learning_Status to the DynamoDB_Table and update the completionPercentage field for that Resource.
2. THE Progress_Tracker SHALL accept Learning_Status values of: Not Started, In Progress, Completed, Skipped.
3. WHEN a User sets a Resource's Learning_Status to Completed, THE Progress_Tracker SHALL record the completion timestamp and trigger the AI_Planner to regenerate recommendations.
4. WHEN a User sets a Resource's Learning_Status to Completed on a new calendar day, THE Progress_Tracker SHALL increment the User's Study_Streak by 1.
5. IF a User does not complete any Resource on a given calendar day, THEN THE Progress_Tracker SHALL reset the User's Study_Streak to 0 at midnight UTC of the following day.
6. WHEN a User's overall completion percentage crosses 25%, 50%, 75%, or 100%, THE Progress_Tracker SHALL record a Milestone event in the DynamoDB_Table with the threshold value and timestamp.
7. IF a User attempts to update the Learning_Status of a Resource that does not belong to their userId, THEN THE Progress_Tracker SHALL return an HTTP 403 response.

---

### Requirement 7: AI Recommendations Refresh

**User Story:** As a learner, I want my recommendations to update automatically whenever my progress changes, so that I am never shown resources I have already completed.

#### Acceptance Criteria

1. WHEN a Resource's Learning_Status is set to Completed, THE AI_Planner SHALL regenerate the User's Learning_Plan excluding that Resource from future scheduled days.
2. WHEN the AI_Planner regenerates a Learning_Plan after a progress update, THE AI_Planner SHALL include a Recommendation_Reason for each newly scheduled Resource that references the User's recent completion (e.g., "You completed IAM Basics — EC2 is the natural next step for AWS compute knowledge").
3. THE AI_Planner SHALL NOT schedule a Resource with Learning_Status Completed or Skipped in any regenerated Learning_Plan.
4. WHEN the AI_Planner completes plan regeneration, THE Dashboard_API SHALL reflect the updated Learning_Plan on the User's next Dashboard load without requiring a manual refresh trigger from the User.
5. IF plan regeneration fails, THEN THE AI_Planner SHALL preserve the last successfully generated Learning_Plan and log the failure to CloudWatch.

---

### Requirement 8: Resource Search and Filtering

**User Story:** As a learner, I want to search and filter my resource library, so that I can quickly find resources relevant to a specific technology, skill, or certification.

#### Acceptance Criteria

1. WHEN a User submits a search query with one or more filter parameters, THE Search_Service SHALL return all Resources matching all supplied filter parameters for that userId.
2. THE Search_Service SHALL support filtering by: technology, difficulty, Resource_Type, certification tag, skill tag, and free-text tag.
3. WHEN multiple filter parameters are supplied, THE Search_Service SHALL return only Resources that satisfy all supplied filters (AND logic).
4. WHEN a search returns no results, THE Search_Service SHALL return an empty list and an HTTP 200 response rather than an error.
5. THE Search_Service SHALL return search results within 2 seconds under normal load conditions.
6. IF a User submits a search with an unrecognized filter key, THEN THE Search_Service SHALL return an HTTP 400 response with a message listing the supported filter keys.

---

### Requirement 9: REST API

**User Story:** As a frontend developer, I want well-defined REST API endpoints, so that the React frontend can reliably communicate with backend Lambda functions.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose the following endpoints: POST /resources, GET /resources, PUT /resources/{id}, DELETE /resources/{id}, POST /analyze, POST /learning-plan, GET /dashboard, PUT /progress/{id}.
2. WHEN any API_Gateway endpoint receives a request without a valid Authorization header, THE API_Gateway SHALL return an HTTP 401 response.
3. THE API_Gateway SHALL validate the Content-Type header on POST and PUT requests and SHALL return an HTTP 415 response if the Content-Type is not application/json.
4. THE API_Gateway SHALL return all responses in JSON format with appropriate HTTP status codes.
5. WHEN a Lambda function returns an unhandled exception, THE API_Gateway SHALL return an HTTP 500 response with a generic error message and SHALL NOT expose internal stack traces or system details to the caller.
6. THE API_Gateway SHALL enforce a per-user request rate limit of 100 requests per minute and SHALL return an HTTP 429 response when this limit is exceeded.

---

### Requirement 10: Infrastructure as Code

**User Story:** As a DevOps engineer, I want all AWS resources provisioned via AWS CDK, so that the infrastructure is repeatable, version-controlled, and follows AWS Well-Architected best practices.

#### Acceptance Criteria

1. THE CDK_Stack SHALL provision: the DynamoDB_Table, all Lambda functions, the API_Gateway, the Amplify_App, IAM roles with least-privilege policies, and CloudWatch log groups.
2. THE CDK_Stack SHALL configure the DynamoDB_Table with on-demand capacity mode and point-in-time recovery enabled.
3. THE CDK_Stack SHALL configure all Lambda functions with a reserved concurrency limit, a CloudWatch log group with a 30-day retention policy, and environment variables for the DynamoDB table name and Bedrock model ID.
4. THE CDK_Stack SHALL configure the API_Gateway with AWS WAF integration and usage plans aligned to the per-user rate limit defined in Requirement 9.
5. WHERE a production deployment target is specified, THE CDK_Stack SHALL enable DynamoDB deletion protection and SHALL NOT use RemovalPolicy.DESTROY on stateful resources.
6. THE CDK_Stack SHALL output the API_Gateway endpoint URL and the Amplify_App URL upon successful deployment.
7. THE CDK_Stack SHALL be deployable using a single `cdk deploy` command after environment variables are configured.

---

### Requirement 11: Frontend Application

**User Story:** As a learner, I want a responsive, modern UI with dark and light mode, so that I can use the application comfortably on any device and in any lighting condition.

#### Acceptance Criteria

1. THE Frontend SHALL render a Dashboard layout with a sidebar navigation, main content area, progress charts, learning timeline, and a Today's Task card.
2. THE Frontend SHALL support both dark mode and light mode, persisting the User's preference in browser local storage.
3. THE Frontend SHALL be responsive and SHALL render correctly on viewport widths of 375px (mobile), 768px (tablet), and 1280px (desktop) and above.
4. WHEN the Frontend is loaded by a User with no active Learning_Plan, THE Frontend SHALL display an onboarding prompt directing the User to set up their Career_Goal.
5. THE Frontend SHALL display a loading indicator whenever an API request is in flight and SHALL display a user-readable error message if the request fails.
6. THE Frontend SHALL update the Dashboard view without a full page reload after a Learning_Status update is successfully submitted.
7. WHERE a User's browser supports the `prefers-color-scheme` media query and the User has not set a manual preference, THE Frontend SHALL apply the system default color scheme on first load.

---

### Requirement 12: Monitoring and Observability

**User Story:** As a platform engineer, I want structured logging and CloudWatch metrics for all backend components, so that I can detect and diagnose issues in production.

#### Acceptance Criteria

1. THE Lambda functions SHALL emit structured JSON logs to CloudWatch for every invocation, including: userId (if available), endpoint path, HTTP status code returned, and execution duration in milliseconds.
2. WHEN a Lambda function invocation results in an error, THE Lambda function SHALL log the error type, a sanitized error message, and the request correlation ID to CloudWatch at ERROR level.
3. THE CDK_Stack SHALL create a CloudWatch Dashboard containing metrics for: Lambda invocation count, Lambda error rate, Lambda P95 duration, API_Gateway 4xx error rate, API_Gateway 5xx error rate, and DynamoDB consumed read/write capacity units.
4. WHEN the Lambda error rate exceeds 5% over a 5-minute window, THE CloudWatch_Alarm SHALL publish a notification to an SNS topic.
5. THE Lambda functions SHALL propagate a correlation ID (generated at the API_Gateway layer) through all downstream calls to Amazon Bedrock and DynamoDB to enable end-to-end request tracing.
