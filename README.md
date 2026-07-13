# LearningPath AI

An AI-powered learning productivity app built on AWS serverless infrastructure. It helps you track learning resources, set career goals, generate personalized learning plans, and monitor your study progress.

---

## Architecture

```
Frontend (React + Vite)
    │
    └── API Gateway (REST) + WAF
            │
            ├── resource-manager      Lambda  →  DynamoDB
            ├── ai-analyzer           Lambda  →  DynamoDB + Bedrock (Nova Lite)
            ├── career-goal-manager   Lambda  →  DynamoDB + ai-planner
            ├── ai-planner            Lambda  →  DynamoDB + Bedrock (Nova Lite)
            ├── dashboard-api         Lambda  →  DynamoDB (read-only)
            ├── progress-tracker      Lambda  →  DynamoDB + EventBridge (midnight cron)
            └── search-service        Lambda  →  DynamoDB (read-only)
```

Infrastructure is managed with AWS CDK (Python). Frontend is hosted on AWS Amplify.

---

## Project Structure

```
.
├── frontend/               React + Vite frontend
│   ├── src/
│   │   ├── pages/          DashboardPage, ResourcesPage, LearningPlanPage, etc.
│   │   ├── components/     Reusable UI components
│   │   ├── api/            API client
│   │   ├── mocks/          MSW mock handlers (local dev)
│   │   └── styles/         Global CSS with theme variables
│   └── amplify.yml         Amplify build spec
│
├── backend/
│   ├── lambdas/            One package per Lambda function
│   │   ├── ai_analyzer/
│   │   ├── ai_planner/
│   │   ├── auth_authorizer/
│   │   ├── career_goal_manager/
│   │   ├── dashboard_api/
│   │   ├── progress_tracker/
│   │   ├── resource_manager/
│   │   └── search_service/
│   └── shared/             Shared utilities used across Lambdas
│
└── infrastructure/         AWS CDK stack (Python)
    ├── app.py
    ├── learningpath_ai/
    │   └── learningpath_ai_stack.py
    └── tests/
```

---

## Prerequisites

- Node.js 18+
- Python 3.11+
- AWS CLI configured (`aws configure`)
- AWS CDK CLI (`npm install -g aws-cdk`)

---

## Local Development

The frontend runs against mock API handlers — no AWS account needed.

```bash
cd frontend
cp .env.example .env.local   # already set to VITE_MOCK_API=true
npm install
npm run dev
```

Open `http://localhost:5173`.

### Run frontend tests

```bash
cd frontend
npm test
```

### Run infrastructure tests

```bash
cd infrastructure
.venv/bin/python -m pytest tests/ -v
```

> Uses the pre-synthesized `cdk.out/LearningPathAiStack.template.json`. No Docker required.

---

## Deployment

### 1. Deploy backend infrastructure (CDK)

```bash
cd infrastructure
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap aws://YOUR_ACCOUNT_ID/us-east-1
cdk deploy --context account=YOUR_ACCOUNT_ID --context region=us-east-1
```

After deploy, note the outputs:
- `LearningPathAI-ApiGatewayUrl` — your REST API endpoint
- `LearningPathAI-AmplifyAppUrl` — your frontend URL

### 2. Deploy frontend (Amplify)

**Option A — Amplify Console (recommended)**

1. Go to [AWS Amplify Console](https://console.aws.amazon.com/amplify)
2. New app → Host web app → connect your Git repo + `main` branch
3. Add environment variables:
   - `VITE_API_BASE_URL` = value from `LearningPathAI-ApiGatewayUrl`
   - `VITE_MOCK_API` = `false`
4. Save and deploy — Amplify uses `frontend/amplify.yml` automatically

**Option B — Manual (drag & drop)**

```bash
cd frontend
npm run build          # outputs to dist/
```

Then in Amplify Console → "Deploy without Git" → drag the `dist/` folder.

---

## API Endpoints

All routes require an `Authorization` header.

| Method | Path | Lambda | Description |
|--------|------|--------|-------------|
| `POST` | `/resources` | resource-manager | Add a learning resource |
| `GET` | `/resources` | resource-manager | List resources |
| `PUT` | `/resources/{id}` | resource-manager | Update a resource |
| `DELETE` | `/resources/{id}` | resource-manager | Delete a resource |
| `POST` | `/analyze` | ai-analyzer | AI analysis of a resource |
| `POST` | `/career-goal` | career-goal-manager | Set career goal |
| `PUT` | `/career-goal` | career-goal-manager | Update career goal |
| `POST` | `/learning-plan` | ai-planner | Generate learning plan |
| `GET` | `/dashboard` | dashboard-api | Dashboard data |
| `PUT` | `/progress/{id}` | progress-tracker | Update progress |
| `PATCH` | `/progress/{id}` | progress-tracker | Partial progress update |
| `GET` | `/search` | search-service | Search resources |

---

## Infrastructure Highlights

- **DynamoDB** — single table `LearningPathAI`, on-demand billing, PITR enabled
- **IAM** — least-privilege roles per Lambda; Bedrock access only for ai-analyzer and ai-planner
- **WAF** — AWS Managed Rules Common Rule Set on API Gateway
- **EventBridge** — midnight UTC cron triggers progress-tracker for streak resets
- **CloudWatch** — 30-day log retention, dashboard, error rate alarms (>5%) → SNS
- **Production** — deletion protection + `RETAIN` removal policy on DynamoDB

---

## Environment Variables

| Variable | Where | Description |
|----------|-------|-------------|
| `VITE_API_BASE_URL` | frontend | API Gateway endpoint URL |
| `VITE_MOCK_API` | frontend | `true` for local mock, `false` for production |
| `DYNAMODB_TABLE_NAME` | Lambda env | Set by CDK automatically |
| `BEDROCK_MODEL_ID` | Lambda env | `amazon.nova-lite-v1:0` |
| `AI_PLANNER_FUNCTION_NAME` | Lambda env | Set by CDK for cross-function invokes |
| `AI_ANALYZER_FUNCTION_NAME` | Lambda env | Set by CDK for cross-function invokes |
