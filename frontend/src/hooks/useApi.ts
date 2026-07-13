import { useState, useCallback } from "react";
import { ApiError } from "../api/client";

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

interface UseApiResult<T> extends ApiState<T> {
  execute: (...args: Parameters<() => Promise<T>>) => Promise<T | null>;
  reset: () => void;
}

/**
 * Wraps an async API call with loading, error, and data state.
 *
 * Usage:
 *   const { data, loading, error, execute } = useApi(() => apiClient.get('/resources'));
 *   useEffect(() => { execute(); }, [execute]);
 */
export function useApi<T>(
  fn: (...args: unknown[]) => Promise<T>
): UseApiResult<T> {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(
    async (...args: unknown[]): Promise<T | null> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const data = await fn(...args);
        setState({ data, loading: false, error: null });
        return data;
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.toUserMessage()
            : "An unexpected error occurred.";
        setState((prev) => ({ ...prev, data: null, loading: false, error: message }));
        return null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn]
  );

  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null });
  }, []);

  return { ...state, execute, reset };
}
