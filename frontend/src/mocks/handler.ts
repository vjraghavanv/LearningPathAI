/**
 * Local development mock API handler.
 *
 * Intercepts fetch calls made by the app and returns realistic in-memory data.
 * Enabled only when VITE_MOCK_API=true (set in .env.local).
 *
 * Supports:
 *   GET  /dashboard
 *   GET  /resources
 *   POST /resources
 *   PUT  /resources/:id
 *   DELETE /resources/:id
 *   GET  /career-goal
 *   POST /career-goal
 *   PUT  /career-goal
 *   GET  /learning-plan
 *   POST /learning-plan
 *   PUT  /progress/:id
 *   GET  /search
 */

import { resources, careerGoal, learningPlan, streak, buildDashboard } from "./data";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function notFound(msg = "Not found"): Response {
  return json({ message: msg }, 404);
}

// Unique ID generator
let _idCounter = 100;
function nextId(): string {
  return String(++_idCounter);
}

// ---------------------------------------------------------------------------
// Route matcher
// ---------------------------------------------------------------------------

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;

const routes: Array<{ method: string; pattern: RegExp; handler: Handler }> = [];

function route(method: string, pattern: RegExp, handler: Handler) {
  routes.push({ method, pattern, handler });
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

route("GET", /\/dashboard/, () => json(buildDashboard()));

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

route("GET", /\/resources$/, () => json(resources));

route("POST", /\/resources$/, async (_url, init) => {
  const body = JSON.parse((init.body as string) ?? "{}");

  if (!body.title || !body.url || !body.resourceType) {
    return json({ error: "VALIDATION_ERROR", message: "title, url, and resourceType are required." }, 400);
  }

  const newResource = {
    userId: "local-user-1",
    resourceId: `RESOURCE#${nextId()}`,
    title: body.title,
    url: body.url,
    resourceType: body.resourceType,
    difficulty: body.difficulty ?? null,
    learningStatus: body.learningStatus ?? "Not Started",
    tags: body.tags ?? [],
    technology: body.technology ?? "",
    estimatedDuration: body.estimatedDuration ?? "",
    aiMetadata: {
      priorityScore: Math.floor(Math.random() * 40) + 60,
      summary: `AI analysis pending for "${body.title}".`,
      skills: body.tags ?? [],
      difficulty: body.difficulty ?? "Beginner",
      estimatedTime: body.estimatedDuration ?? "1 hour",
      whyLearnNow: "This resource aligns with your current career goal.",
      recommendedWeek: 1,
    },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  resources.push(newResource);
  return json(newResource, 201);
});

route("PUT", /\/resources\/(.+)$/, async (url, init) => {
  const id = url.pathname.split("/").pop()!;
  const idx = resources.findIndex((r) => r.resourceId === id || r.resourceId === `RESOURCE#${id}`);
  if (idx === -1) return notFound();

  const body = JSON.parse((init.body as string) ?? "{}");
  const updated = { ...resources[idx], ...body, updatedAt: new Date().toISOString() };
  resources[idx] = updated;
  return json(updated);
});

route("DELETE", /\/resources\/(.+)$/, (url) => {
  const id = url.pathname.split("/").pop()!;
  const idx = resources.findIndex((r) => r.resourceId === id || r.resourceId === `RESOURCE#${id}`);
  if (idx === -1) return notFound();
  resources.splice(idx, 1);
  return new Response(null, { status: 204 });
});

// ---------------------------------------------------------------------------
// Career Goal
// ---------------------------------------------------------------------------

let _careerGoal: typeof careerGoal | null = { ...careerGoal };

route("GET", /\/career-goal$/, () => {
  if (!_careerGoal) return notFound("No career goal set yet.");
  return json(_careerGoal);
});

route("POST", /\/career-goal$/, async (_url, init) => {
  const body = JSON.parse((init.body as string) ?? "{}");
  _careerGoal = {
    userId: "local-user-1",
    ...body,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  return json(_careerGoal, 201);
});

route("PUT", /\/career-goal$/, async (_url, init) => {
  const body = JSON.parse((init.body as string) ?? "{}");
  _careerGoal = { ..._careerGoal!, ...body, updatedAt: new Date().toISOString() };
  return json(_careerGoal);
});

// ---------------------------------------------------------------------------
// Learning Plan
// ---------------------------------------------------------------------------

let _plan: typeof learningPlan | null = { ...learningPlan };

route("GET", /\/learning-plan$/, () => {
  if (!_plan) return notFound("No learning plan generated yet.");
  return json(_plan);
});

route("POST", /\/learning-plan$/, () => {
  // Simulate regeneration — just refresh generatedAt
  _plan = { ...(learningPlan), generatedAt: new Date().toISOString() };
  return json(_plan);
});

// ---------------------------------------------------------------------------
// Progress
// ---------------------------------------------------------------------------

route("PUT", /\/progress\/(.+)$/, async (url, init) => {
  const id = url.pathname.split("/").pop()!;
  const idx = resources.findIndex((r) => r.resourceId === id || r.resourceId === `RESOURCE#${id}`);
  if (idx === -1) return notFound();

  const body = JSON.parse((init.body as string) ?? "{}");
  const newStatus = body.learningStatus;
  const validStatuses = ["Not Started", "In Progress", "Completed", "Skipped"];
  if (!validStatuses.includes(newStatus)) {
    return json({ error: "VALIDATION_ERROR", message: `learningStatus must be one of: ${validStatuses.join(", ")}` }, 400);
  }

  resources[idx] = { ...resources[idx], learningStatus: newStatus, updatedAt: new Date().toISOString() };

  if (newStatus === "Completed") {
    streak.currentStreak += 1;
    streak.lastCompletionDate = new Date().toISOString().split("T")[0];
  }

  return json(resources[idx]);
});

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

route("GET", /\/search/, (url) => {
  const technology = url.searchParams.get("technology");
  const difficulty = url.searchParams.get("difficulty");
  const resourceType = url.searchParams.get("resourceType");
  const skillTag = url.searchParams.get("skillTag");
  const certificationTag = url.searchParams.get("certificationTag");
  const tag = url.searchParams.get("tag");

  const VALID_KEYS = new Set(["technology", "difficulty", "resourceType", "skillTag", "certificationTag", "tag"]);
  for (const key of url.searchParams.keys()) {
    if (!VALID_KEYS.has(key)) {
      return json({ error: "VALIDATION_ERROR", message: `Unrecognized filter key: "${key}". Supported: ${[...VALID_KEYS].join(", ")}` }, 400);
    }
  }

  let results = [...resources];
  if (technology) results = results.filter((r) => r.technology?.toLowerCase().includes(technology.toLowerCase()));
  if (difficulty) results = results.filter((r) => r.difficulty === difficulty);
  if (resourceType) results = results.filter((r) => r.resourceType === resourceType);
  if (skillTag) results = results.filter((r) => r.aiMetadata?.skills?.some((s: string) => s.toLowerCase().includes(skillTag.toLowerCase())));
  if (certificationTag) results = results.filter((r) => r.tags?.some((t: string) => t.toLowerCase().includes(certificationTag.toLowerCase())));
  if (tag) results = results.filter((r) => r.tags?.some((t: string) => t.toLowerCase().includes(tag.toLowerCase())));

  return json(results);
});

// ---------------------------------------------------------------------------
// Main intercept function
// ---------------------------------------------------------------------------

const originalFetch = window.fetch.bind(window);

export function installMockHandler() {
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();

    // Only intercept relative paths or paths that match our API routes
    const isApiCall = typeof request === "string" && (
      request.startsWith("/") ||
      request.includes("localhost") ||
      request.includes("127.0.0.1")
    );

    if (!isApiCall) {
      return originalFetch(input, init);
    }

    const urlStr = request.startsWith("http")
      ? request
      : `http://localhost${request}`;

    let url: URL;
    try {
      url = new URL(urlStr);
    } catch {
      return originalFetch(input, init);
    }

    for (const { method: m, pattern, handler } of routes) {
      if (m === method && pattern.test(url.pathname)) {
        // Simulate ~200ms network delay so loading states are visible
        await new Promise((res) => setTimeout(res, 200));
        try {
          return await handler(url, init ?? {});
        } catch (err) {
          console.error("[MockAPI] Handler error:", err);
          return json({ message: "Mock API internal error" }, 500);
        }
      }
    }

    // No mock matched — log and return 404
    console.warn(`[MockAPI] No handler for ${method} ${url.pathname}`);
    return json({ message: `No mock for ${method} ${url.pathname}` }, 404);
  };

  console.info("[MockAPI] 🟢 Mock API active — all requests intercepted locally");
}

export function uninstallMockHandler() {
  window.fetch = originalFetch;
}
