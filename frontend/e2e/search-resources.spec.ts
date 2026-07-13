/**
 * E2E Test: User searches resources with multiple filters → correct results returned
 *
 * Scenario:
 * 1. User navigates to the Search page
 * 2. User selects Technology = "AWS" and Difficulty = "Beginner"
 * 3. User submits the search → only resources matching BOTH filters are shown (AND logic)
 * 4. User clears filters → result count resets
 * 5. Searching with no matching results shows a "No resources" message (HTTP 200, empty list)
 *
 * Requirements validated:
 * - Req 8.1: Returns all matching resources for the userId
 * - Req 8.2: Supports filtering by technology, difficulty, resourceType, skill/cert/tag
 * - Req 8.3: AND logic — only resources satisfying all filters are returned
 * - Req 8.4: No results → HTTP 200 with empty list, not an error
 * - Property 22: Search returns all matching resources with AND logic
 */

import { test, expect } from "@playwright/test";
import { mockSearchFlow } from "./helpers/mock-api";

test.describe("Resource search with multiple filters", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearchFlow(page);
  });

  test("search page renders filter form", async ({ page }) => {
    await page.goto("/search");

    // All filter fields should be present (Requirement 8.2)
    await expect(page.getByLabel(/technology/i)).toBeVisible({ timeout: 8000 });
    await expect(page.getByLabel(/difficulty/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByLabel(/resource type/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByLabel(/skill tag/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: /search/i })).toBeVisible({ timeout: 5000 });
  });

  test("single filter returns matching resources", async ({ page }) => {
    await page.goto("/search");

    // Filter by technology = "AWS"
    await page.getByLabel(/technology/i).fill("AWS");
    await page.getByRole("button", { name: /search/i }).click();

    // Should show 2 AWS resources (r001 and r003 from the mock)
    await expect(page.getByText(/2 resource/i)).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("AWS IAM Deep Dive")).toBeVisible();
    await expect(page.getByText("AWS EC2 Overview")).toBeVisible();

    // Non-AWS resource should not appear
    await expect(page.getByText("Docker Fundamentals")).not.toBeVisible();
  });

  test("AND logic: two filters return only resources matching both", async ({ page }) => {
    await page.goto("/search");

    // Filter by technology = "AWS" AND difficulty = "Beginner"
    // Only r001 (AWS + Beginner) should match; r003 (AWS + Intermediate) should not
    await page.getByLabel(/technology/i).fill("AWS");
    await page.getByLabel(/difficulty/i).selectOption("Beginner");
    await page.getByRole("button", { name: /search/i }).click();

    // Only 1 resource matches both filters (Requirement 8.3, Property 22)
    await expect(page.getByText(/1 resource/i)).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("AWS IAM Deep Dive")).toBeVisible();
    await expect(page.getByText("AWS EC2 Overview")).not.toBeVisible();
    await expect(page.getByText("Docker Fundamentals")).not.toBeVisible();
  });

  test("no results shows empty state message with HTTP 200 (no error)", async ({ page }) => {
    await page.goto("/search");

    // Filter by technology that has no resources — the mock returns empty list for unknown tech
    await page.getByLabel(/technology/i).fill("Kubernetes");
    await page.getByRole("button", { name: /search/i }).click();

    // Should show "No resources" message — NOT an error banner (Requirement 8.4)
    await expect(
      page.getByText(/no resources match/i)
    ).toBeVisible({ timeout: 8000 });

    // Error banner should NOT appear (empty list is not an error)
    await expect(
      page.getByRole("alert").filter({ hasText: /error|failed/i })
    ).not.toBeVisible();
  });

  test("resource type filter returns correct subset", async ({ page }) => {
    await page.goto("/search");

    // Filter by resourceType = "Online Course"
    // Only r002 (Docker + Online Course) should match
    await page.getByLabel(/resource type/i).selectOption("Online Course");
    await page.getByRole("button", { name: /search/i }).click();

    await expect(page.getByText(/1 resource/i)).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("Docker Fundamentals")).toBeVisible();
    await expect(page.getByText("AWS IAM Deep Dive")).not.toBeVisible();
  });

  test("clearing filters resets the results", async ({ page }) => {
    await page.goto("/search");

    // Apply a filter
    await page.getByLabel(/technology/i).fill("AWS");
    await page.getByRole("button", { name: /search/i }).click();
    await expect(page.getByText(/2 resource/i)).toBeVisible({ timeout: 8000 });

    // Clear filters
    await page.getByRole("button", { name: /clear filters/i }).click();

    // Results should be cleared (form reset, no result count shown)
    await expect(page.getByText(/resources? found/i)).not.toBeVisible();
    await expect(page.getByLabel(/technology/i)).toHaveValue("");
  });

  test("all three filters together narrow results correctly", async ({ page }) => {
    await page.goto("/search");

    // technology=AWS, difficulty=Intermediate, resourceType=Technical Article
    // Only r003 matches all three
    await page.getByLabel(/technology/i).fill("AWS");
    await page.getByLabel(/difficulty/i).selectOption("Intermediate");
    await page.getByLabel(/resource type/i).selectOption("Technical Article");
    await page.getByRole("button", { name: /search/i }).click();

    await expect(page.getByText(/1 resource/i)).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("AWS EC2 Overview")).toBeVisible();
    await expect(page.getByText("AWS IAM Deep Dive")).not.toBeVisible();
    await expect(page.getByText("Docker Fundamentals")).not.toBeVisible();
  });
});
