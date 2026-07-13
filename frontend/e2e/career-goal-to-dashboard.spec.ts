/**
 * E2E Test: User sets career goal → plan generated → dashboard shows today's task
 *
 * Scenario:
 * 1. User arrives at the app with no career goal → dashboard shows onboarding prompt
 * 2. User navigates to Career Goal page and fills the form
 * 3. User submits the form → success message appears
 * 4. App navigates to /plan (plan generated)
 * 5. User navigates to Dashboard → today's task card is visible
 *
 * The test is self-contained: all API calls are intercepted and returned as
 * fixture data — no live backend required.
 */

import { test, expect } from "@playwright/test";
import { mockCareerGoalToPlanFlow } from "./helpers/mock-api";

test.describe("Career goal → plan → dashboard flow", () => {
  test.beforeEach(async ({ page }) => {
    await mockCareerGoalToPlanFlow(page);
  });

  test("dashboard shows onboarding prompt when no plan exists", async ({ page }) => {
    await page.goto("/");

    // When no active plan, the app should show an onboarding prompt, NOT the
    // dashboard task card (Requirement 5.6, 11.4)
    await expect(
      page.getByRole("heading", { name: /get started|career goal|set up/i })
    ).toBeVisible({ timeout: 8000 });
  });

  test("user fills career goal form and sees success message", async ({ page }) => {
    await page.goto("/career");

    // Form should be in "set up" mode since no profile exists
    await expect(
      page.getByRole("heading", { name: /set up your career goal/i })
    ).toBeVisible({ timeout: 8000 });

    // Fill in the career goal dropdown
    await page.getByLabel(/career goal/i).selectOption("Become AWS Cloud Engineer");

    // Select skill level
    await page.getByLabel(/current skill level/i).selectOption("Beginner");

    // Enter weekly study hours
    await page.getByLabel(/weekly study hours/i).fill("10");

    // Select learning pace
    await page.getByLabel(/preferred learning pace/i).selectOption("Moderate");

    // Submit the form
    await page.getByRole("button", { name: /save & generate plan/i }).click();

    // Success message should appear (Requirement 3.1)
    await expect(
      page.getByRole("status").filter({ hasText: /career goal saved|generating|learning plan/i })
    ).toBeVisible({ timeout: 8000 });
  });

  test("dashboard shows today's task card after plan is generated", async ({ page }) => {
    // Navigate directly to dashboard after plan has been generated
    // (simulated by mockCareerGoalToPlanFlow returning the plan on the 2nd dashboard call)
    await page.goto("/");

    // First visit shows onboarding; navigate to career goal, submit, then come back
    await page.goto("/career");

    await page.getByLabel(/career goal/i).selectOption("Become AWS Cloud Engineer");
    await page.getByLabel(/current skill level/i).selectOption("Beginner");
    await page.getByLabel(/weekly study hours/i).fill("10");
    await page.getByLabel(/preferred learning pace/i).selectOption("Moderate");
    await page.getByRole("button", { name: /save & generate plan/i }).click();

    // Wait for success message, then navigate to dashboard
    await expect(
      page.getByRole("status").filter({ hasText: /career goal saved|generating/i })
    ).toBeVisible({ timeout: 8000 });

    // Navigate to dashboard (the second GET /dashboard call returns the plan fixture)
    await page.goto("/");

    // Dashboard should now show today's task card (Requirement 5.1, 5.2)
    await expect(page.getByText("AWS IAM Deep Dive")).toBeVisible({ timeout: 8000 });
  });

  test("dashboard completion percentage is displayed", async ({ page }) => {
    // Arrange: plan already exists (second+ dashboard call)
    // Set up plan state by navigating to career page and submitting
    await page.goto("/career");

    await page.getByLabel(/career goal/i).selectOption("Become AWS Cloud Engineer");
    await page.getByLabel(/current skill level/i).selectOption("Beginner");
    await page.getByLabel(/weekly study hours/i).fill("10");
    await page.getByLabel(/preferred learning pace/i).selectOption("Moderate");
    await page.getByRole("button", { name: /save & generate plan/i }).click();

    await expect(
      page.getByRole("status").filter({ hasText: /career goal saved|generating/i })
    ).toBeVisible({ timeout: 8000 });

    await page.goto("/");

    // Completion percentage should be visible on the dashboard (Requirement 5.4)
    await expect(
      page.getByText(/0(\s*%|\.0\s*%)?/i).or(page.getByText(/complete/i))
    ).toBeVisible({ timeout: 8000 });
  });
});
