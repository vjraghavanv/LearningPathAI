import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import { useApi } from "../hooks/useApi";
import { OnboardingPrompt } from "../components/OnboardingPrompt";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorBanner } from "../components/ErrorBanner";
import { TodaysTaskCard, TodaysTask } from "../components/TodaysTaskCard";
import { ProgressRing } from "../components/ProgressRing";
import { WeeklyProgressBar, WeeklyProgressEntry } from "../components/WeeklyProgressBar";
import { LearningTimeline } from "../components/LearningTimeline";
import { StreakDisplay } from "../components/StreakDisplay";
import { PriorityResources, PriorityResource } from "../components/PriorityResources";
import { CertificationRecommendations } from "../components/CertificationRecommendations";

export interface DashboardResponse {
  todaysTask: TodaysTask | null;
  completionPercentage: number | null;
  studyStreak: number | null;
  weeklyProgress: WeeklyProgressEntry[] | null;
  roadmap: string[] | null;
  priorityResources: PriorityResource[];
  certificationRecommendations: string[];
  recommendedProjects: string[];
  message?: string;
}

export type LearningStatusChange = "In Progress" | "Completed" | "Skipped";

/**
 * Applies an optimistic update to a local copy of the dashboard response.
 *
 * Rules:
 * - Updates the matching resource's learningStatus in priorityResources
 * - If the new status is "Completed", increments the study streak by 1
 * - If the new status is "Completed", recomputes completionPercentage using
 *   the formula: (count of Completed) / (count of non-Skipped) * 100,
 *   rounded to 1 decimal place (Requirement 5.4 / Property 17)
 * - If the new status is "Skipped", recomputes completionPercentage
 *   (the resource is removed from the denominator)
 */
export function applyOptimisticStatusUpdate(
  current: DashboardResponse,
  resourceId: string,
  newStatus: LearningStatusChange
): DashboardResponse {
  // Update priorityResources: set learningStatus on matching resource
  const updatedPriorityResources = current.priorityResources.map((r) =>
    r.resourceId === resourceId ? { ...r, learningStatus: newStatus } : r
  );

  // Optimistically increment streak if status is "Completed"
  const updatedStreak =
    newStatus === "Completed" && current.studyStreak != null
      ? current.studyStreak + 1
      : current.studyStreak;

  // Recompute completionPercentage for Completed or Skipped changes
  // Formula: (count Completed) / (count non-Skipped) * 100, rounded to 1 decimal
  let updatedPercentage = current.completionPercentage;
  if (
    (newStatus === "Completed" || newStatus === "Skipped") &&
    current.completionPercentage != null
  ) {
    // After applying the new status to updatedPriorityResources,
    // recompute using the updated list
    const completedCount = updatedPriorityResources.filter(
      (r) => r.learningStatus === "Completed"
    ).length;
    const nonSkippedCount = updatedPriorityResources.filter(
      (r) => r.learningStatus !== "Skipped"
    ).length;

    if (nonSkippedCount > 0) {
      updatedPercentage = Math.round((completedCount / nonSkippedCount) * 1000) / 10;
    } else {
      // All resources skipped — 0% (no denominator)
      updatedPercentage = 0;
    }
  }

  return {
    ...current,
    priorityResources: updatedPriorityResources,
    studyStreak: updatedStreak,
    completionPercentage: updatedPercentage,
  };
}

export function DashboardPage() {
  const { data, loading, error, execute, reset } = useApi<DashboardResponse>(
    () => apiClient.get("/dashboard")
  );

  // Local optimistic copy of dashboard data — initialized from server data,
  // updated immediately on status change before background re-fetch completes.
  const [optimisticData, setOptimisticData] = useState<DashboardResponse | null>(null);

  // Snapshot of data before an optimistic update, used to revert on API failure.
  const prevDataSnapshot = useRef<DashboardResponse | null>(null);

  // Non-blocking error shown when a background re-fetch fails after optimistic update.
  const [backgroundError, setBackgroundError] = useState<string | null>(null);

  // Keep optimisticData in sync with fresh server data after re-fetches.
  // Clear any background error once fresh data arrives.
  useEffect(() => {
    if (data != null) {
      setOptimisticData(data);
      setBackgroundError(null);
    }
  }, [data]);

  useEffect(() => {
    execute();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Immediately applies a local optimistic update for the given resource status
   * change, then kicks off a background re-fetch to reconcile with the server.
   * The full LoadingSpinner is NOT shown during the re-fetch — only on initial load.
   *
   * If the background re-fetch fails, the optimistic data is reverted to the
   * snapshot taken before the update, and a user-readable error is shown.
   */
  const handleStatusChange = useCallback(
    async (resourceId: string, newStatus: LearningStatusChange) => {
      // Snapshot current state before applying optimistic update so we can revert
      setOptimisticData((prev) => {
        if (prev == null) return prev;
        prevDataSnapshot.current = prev;
        return applyOptimisticStatusUpdate(prev, resourceId, newStatus);
      });

      // Background re-fetch — reconciles optimistic state with real server data.
      // On failure, revert the optimistic update and surface a user-readable error.
      const refreshed = await execute();
      if (refreshed === null) {
        // execute() returned null meaning the re-fetch failed; revert to snapshot
        setOptimisticData(prevDataSnapshot.current);
        setBackgroundError(
          "Status updated, but dashboard failed to refresh. Showing previous data."
        );
      }
    },
    [execute]
  );

  // Only show the full-page loading spinner on the very first load (no data yet).
  if (loading && data === null) return <LoadingSpinner label="Loading dashboard…" />;
  if (error && data === null) return <ErrorBanner message={error} onDismiss={reset} />;

  // Use optimistic data if available, fall back to raw server data
  const display = optimisticData ?? data;

  // No active plan — the API returns null plan fields and a message prompt
  const hasNoPlan =
    !display ||
    (display.todaysTask === null &&
      display.completionPercentage === null &&
      display.roadmap === null);

  if (hasNoPlan) {
    return <OnboardingPrompt />;
  }

  return (
    <div>
      <h1>Dashboard</h1>

      {/* Non-blocking background refresh error (shown inline, doesn't replace page) */}
      {backgroundError && (
        <ErrorBanner
          message={backgroundError}
          onDismiss={() => setBackgroundError(null)}
        />
      )}

      {display?.todaysTask && (
        <TodaysTaskCard
          task={display.todaysTask}
          onStatusChange={handleStatusChange}
        />
      )}
      <StreakDisplay streak={display?.studyStreak ?? null} />
      <div>
        <h2>Progress</h2>
        {display?.completionPercentage != null && (
          <ProgressRing
            percentage={display.completionPercentage}
            label="Complete"
          />
        )}
        <WeeklyProgressBar entries={display?.weeklyProgress ?? null} />
      </div>
      <LearningTimeline roadmap={display?.roadmap ?? null} />
      <PriorityResources resources={display?.priorityResources ?? []} />
      <CertificationRecommendations
        certifications={display?.certificationRecommendations ?? []}
        projects={display?.recommendedProjects ?? []}
      />
    </div>
  );
}
