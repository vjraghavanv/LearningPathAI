/**
 * Shared API mock helpers for Playwright E2E tests.
 *
 * These helpers intercept fetch calls via Playwright's `page.route()` and
 * return deterministic fixture data so that tests are fully self-contained
 * and do not require a live backend.
 *
 * Each helper function wires the routes needed for a specific test scenario.
 */

import type { Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

/** A realistic career goal profile returned after POST /career-goal */
export const CAREER_GOAL_FIXTURE = {
  userId: "e2e-user-1",
  careerGoal: "Become AWS Cloud Engineer",
  currentSkillLevel: "Beginner",
  weeklyStudyHours: 10,
  preferredLearningPace: "Moderate",
  createdAt: "2026-07-13T10:00:00Z",
  updatedAt: "2026-07-13T10:00:00Z",
};

/** A minimal resource used in plan + progress tests */
export const RESOURCE_FIXTURE = {
  userId: "e2e-user-1",
  resourceId: "RESOURCE#e2e-resource-001",
  title: "AWS IAM Deep Dive",
  url: "https://docs.aws.amazon.com/iam",
  resourceType: "Documentation",
  difficulty: "Beginner",
  learningStatus: "Not Started",
  tags: ["aws", "iam"],
  technology: "AWS",
  estimatedDuration: "2 hours",
  aiMetadata: {
    priorityScore: 85,
    summary: "Comprehensive guide to AWS Identity and Access Management.",
    skills: ["IAM", "Security"],
    difficulty: "Beginner",
    estimatedTime: "2 hours",
    whyLearnNow: "IAM is foundational for AWS certification.",
    recommendedWeek: 1,
  },
  createdAt: "2026-07-13T09:00:00Z",
  updatedAt: "2026-07-13T09:00:00Z",
};

/** The date string matching "today" in test context */
const TODAY = "2026-07-13";

/** Active learning plan returned after POST /learning-plan */
export const PLAN_FIXTURE = {
  userId: "e2e-user-1",
  resourceId: "PLAN#active",
  dailySchedule: Array.from({ length: 7 }, (_, i) => ({
    day: i + 1,
    date: TODAY,
    resourceId: "RESOURCE#e2e-resource-001",
    estimatedDuration: "2 hours",
    recommendationReason: "IAM is the foundation of AWS security.",
  })),
  weeklyRoadmap: ["Week 1: IAM Fundamentals", "Week 2: EC2 Basics"],
  recommendedProjects: ["Build a serverless API with Lambda + API Gateway"],
  certificationRecommendations: ["AWS SAA-C03"],
  estimatedCompletionTimeline: "3 months",
  generatedAt: "2026-07-13T10:01:00Z",
};

/** Dashboard response when a plan exists */
export const DASHBOARD_WITH_PLAN_FIXTURE = {
  userId: "e2e-user-1",
  todaysTask: {
    resourceId: "RESOURCE#e2e-resource-001",
    title: "AWS IAM Deep Dive",
    url: "https://docs.aws.amazon.com/iam",
    resourceType: "Documentation",
    estimatedDuration: "2 hours",
    recommendationReason: "IAM is the foundation of AWS security.",
    learningStatus: "Not Started",
    priorityScore: 85,
  },
  completionPercentage: 0.0,
  studyStreak: 0,
  weeklyProgress: [
    { day: "Mon", completedMinutes: 0, targetMinutes: 86 },
    { day: "Tue", completedMinutes: 0, targetMinutes: 86 },
  ],
  roadmap: ["Week 1: IAM Fundamentals", "Week 2: EC2 Basics"],
  priorityResources: [
    {
      resourceId: "RESOURCE#e2e-resource-001",
      title: "AWS IAM Deep Dive",
      url: "https://docs.aws.amazon.com/iam",
      resourceType: "Documentation",
      difficulty: "Beginner",
      learningStatus: "Not Started",
      priorityScore: 85,
      recommendationReason: "IAM is the foundation of AWS security.",
    },
  ],
  certificationRecommendations: ["AWS SAA-C03"],
  recommendedProjects: ["Build a serverless API with Lambda + API Gateway"],
  message: null,
};

/** Dashboard response when no plan exists (onboarding state) */
export const DASHBOARD_NO_PLAN_FIXTURE = {
  userId: "e2e-user-1",
  todaysTask: null,
  completionPercentage: null,
  studyStreak: null,
  weeklyProgress: null,
  roadmap: null,
  priorityResources: [],
  certificationRecommendations: [],
  recommendedProjects: [],
  message: "Set up your Career Goal to generate a personalised learning plan.",
};

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

/** Injects a Bearer token so the API client includes Authorization headers. */
export async function injectAuthToken(page: Page, token = "e2e-test-token") {
  await page.addInitScript((t) => {
    sessionStorage.setItem("lp-ai-token", t);
  }, token);
}

/** Suppress any errors from un-mocked routes so tests stay clean. */
export async function suppressUnmockedRoutes(page: Page) {
  await page.route("**/*", (route) => {
    // Only suppress unhandled API routes; let page navigation through
    if (route.request().url().includes("/api/") && !route.request().isNavigationRequest()) {
      route.fulfill({ status: 200, contentType: "application/json", body: "null" });
    } else {
      route.fallback();
    }
  });
}

/**
 * Wires all API mocks needed for the "career goal → plan → dashboard" flow.
 *
 * Scenario:
 * 1. GET /career-goal → 404 (no profile yet)
 * 2. POST /career-goal → 201 with CAREER_GOAL_FIXTURE
 * 3. POST /learning-plan → 200 with PLAN_FIXTURE
 * 4. GET /dashboard (first call, before plan) → DASHBOARD_NO_PLAN_FIXTURE
 * 5. GET /dashboard (after plan generated) → DASHBOARD_WITH_PLAN_FIXTURE
 */
export async function mockCareerGoalToPlanFlow(page: Page) {
  await injectAuthToken(page);

  let dashboardCallCount = 0;

  // Career goal: not yet set
  await page.route("**/career-goal", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ message: "Not found" }) });
    } else if (route.request().method() === "POST") {
      route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(CAREER_GOAL_FIXTURE) });
    } else {
      route.fallback();
    }
  });

  // Learning plan generation
  await page.route("**/learning-plan", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(PLAN_FIXTURE) });
    } else {
      route.fallback();
    }
  });

  // Dashboard: first call returns no-plan, subsequent calls return with-plan
  await page.route("**/dashboard", (route) => {
    dashboardCallCount++;
    const fixture = dashboardCallCount <= 1 ? DASHBOARD_NO_PLAN_FIXTURE : DASHBOARD_WITH_PLAN_FIXTURE;
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) });
  });

  // Resources
  await page.route("**/resources", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([RESOURCE_FIXTURE]) });
    } else {
      route.fallback();
    }
  });
}

/**
 * Wires all API mocks needed for "mark resource complete → streak increments → plan regenerates".
 */
export async function mockProgressAndStreakFlow(page: Page) {
  await injectAuthToken(page);

  let dashboardCallCount = 0;
  let progressUpdated = false;

  // Resources list
  await page.route("**/resources", (route) => {
    if (route.request().method() === "GET") {
      const resource = progressUpdated
        ? { ...RESOURCE_FIXTURE, learningStatus: "Completed" }
        : RESOURCE_FIXTURE;
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([resource]) });
    } else {
      route.fallback();
    }
  });

  // Progress update
  await page.route("**/progress/**", (route) => {
    if (route.request().method() === "PUT") {
      progressUpdated = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...RESOURCE_FIXTURE, learningStatus: "Completed" }),
      });
    } else {
      route.fallback();
    }
  });

  // Learning plan regeneration
  await page.route("**/learning-plan", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(PLAN_FIXTURE) });
    } else {
      route.fallback();
    }
  });

  // Dashboard: after progress update, streak is 1 and resource is completed
  await page.route("**/dashboard", (route) => {
    dashboardCallCount++;
    if (!progressUpdated || dashboardCallCount <= 1) {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DASHBOARD_WITH_PLAN_FIXTURE) });
    } else {
      // After completion, streak increments to 1
      const updated = {
        ...DASHBOARD_WITH_PLAN_FIXTURE,
        studyStreak: 1,
        completionPercentage: 100.0,
        priorityResources: [
          { ...DASHBOARD_WITH_PLAN_FIXTURE.priorityResources[0], learningStatus: "Completed" },
        ],
      };
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(updated) });
    }
  });

  // Career goal
  await page.route("**/career-goal", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CAREER_GOAL_FIXTURE) });
    } else {
      route.fallback();
    }
  });
}

/**
 * Wires mocks for the "search resources with multiple filters" flow.
 */
export async function mockSearchFlow(page: Page) {
  await injectAuthToken(page);

  const allResources = [
    {
      ...RESOURCE_FIXTURE,
      resourceId: "RESOURCE#r001",
      title: "AWS IAM Deep Dive",
      technology: "AWS",
      difficulty: "Beginner",
      resourceType: "Documentation",
    },
    {
      ...RESOURCE_FIXTURE,
      resourceId: "RESOURCE#r002",
      title: "Docker Fundamentals",
      technology: "Docker",
      difficulty: "Intermediate",
      resourceType: "Online Course",
    },
    {
      ...RESOURCE_FIXTURE,
      resourceId: "RESOURCE#r003",
      title: "AWS EC2 Overview",
      technology: "AWS",
      difficulty: "Intermediate",
      resourceType: "Technical Article",
    },
  ];

  await page.route("**/search**", (route) => {
    // Skip navigation requests — only intercept API fetch calls to /search
    if (route.request().isNavigationRequest()) {
      route.fallback();
      return;
    }

    const url = new URL(route.request().url());
    const technology = url.searchParams.get("technology");
    const difficulty = url.searchParams.get("difficulty");
    const resourceType = url.searchParams.get("resourceType");

    let results = allResources;
    if (technology) results = results.filter((r) => r.technology === technology);
    if (difficulty) results = results.filter((r) => r.difficulty === difficulty);
    if (resourceType) results = results.filter((r) => r.resourceType === resourceType);

    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(results) });
  });

  await page.route("**/resources", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(allResources) });
    } else {
      route.fallback();
    }
  });

  await page.route("**/dashboard", (route) => {
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DASHBOARD_WITH_PLAN_FIXTURE) });
  });

  await page.route("**/career-goal", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CAREER_GOAL_FIXTURE) });
    } else {
      route.fallback();
    }
  });
}
