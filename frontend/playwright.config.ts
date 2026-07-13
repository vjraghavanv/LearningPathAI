import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration for LearningPath AI.
 *
 * Tests run against a locally served Vite dev build (or preview build).
 * The base URL is read from PLAYWRIGHT_BASE_URL env var; defaults to
 * http://localhost:5173 (Vite default).
 *
 * To run against a real API, set VITE_API_BASE_URL in the environment before
 * starting the dev server. When no real API is available, tests rely on the
 * mock service worker (MSW) that is automatically activated in test mode.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Start the Vite preview server automatically when running E2E tests
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
