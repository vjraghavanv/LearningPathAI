/**
 * Global API client
 *
 * - Injects Authorization header from sessionStorage/localStorage
 * - Normalises errors into user-readable ApiError instances
 * - Provides typed request helpers used by feature modules
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly statusCode: number,
    message: string,
    public readonly field?: string
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Returns a user-readable sentence suitable for display in the UI. */
  toUserMessage(): string {
    switch (this.statusCode) {
      case 400:
        return this.field
          ? `Invalid input for "${this.field}": ${this.message}`
          : `Invalid input: ${this.message}`;
      case 401:
        return "Your session has expired. Please sign in again.";
      case 403:
        return "You don't have permission to perform that action.";
      case 404:
        return "The requested resource was not found.";
      case 415:
        return "Unsupported request format.";
      case 429:
        return "Too many requests. Please wait a moment and try again.";
      case 503:
        return this.message || "Service temporarily unavailable. Please try again shortly.";
      default:
        return "Something went wrong. Please try again.";
    }
  }
}

// ---------------------------------------------------------------------------
// Token retrieval — swap this out for your auth provider (Cognito, etc.)
// ---------------------------------------------------------------------------

function getToken(): string | null {
  return (
    sessionStorage.getItem("lp-ai-token") ??
    localStorage.getItem("lp-ai-token") ??
    import.meta.env.VITE_DEV_TOKEN ??
    null
  );
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let message = response.statusText;
    let field: string | undefined;

    try {
      const json = await response.json();
      message = json.message ?? json.error ?? message;
      field = json.field;
    } catch {
      // non-JSON error body — use status text
    }

    throw new ApiError(response.status, message, field);
  }

  // 204 No Content
  if (response.status === 204) return undefined as unknown as T;

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public helpers
// ---------------------------------------------------------------------------

export const apiClient = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};
