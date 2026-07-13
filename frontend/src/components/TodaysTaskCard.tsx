import { useState } from "react";
import { apiClient, ApiError } from "../api/client";
import { LearningStatusChange } from "../pages/DashboardPage";
import "./TodaysTaskCard.css";

export interface TodaysTask {
  resourceId: string;
  estimatedDuration: string;
  recommendationReason: string;
  day: number;
  date: string; // ISO 8601
  /** Optional title resolved by the parent from priorityResources or roadmap */
  title?: string;
}

interface TodaysTaskCardProps {
  task: TodaysTask;
  /**
   * Called after a successful status update so the parent can refresh data.
   * Receives the resourceId and new status so the parent can apply an
   * optimistic update before the background re-fetch completes.
   */
  onStatusChange?: (resourceId: string, newStatus: LearningStatusChange) => void;
}

type UpdateStatus = "idle" | "loading" | "error";

/**
 * Displays today's recommended learning task and lets the user
 * mark it as "In Progress" or "Completed" via PUT /progress/{resourceId}.
 */
export function TodaysTaskCard({ task, onStatusChange }: TodaysTaskCardProps) {
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const displayTitle = task.title ?? `Resource ${task.resourceId}`;

  const formattedDate = (() => {
    try {
      return new Date(task.date).toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
      });
    } catch {
      return task.date;
    }
  })();

  async function updateStatus(learningStatus: LearningStatusChange) {
    setStatus("loading");
    setErrorMsg(null);
    try {
      await apiClient.put(`/progress/${task.resourceId}`, {
        status: learningStatus,
      });
      setStatus("idle");
      onStatusChange?.(task.resourceId, learningStatus);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.toUserMessage()
          : "Failed to update status. Please try again.";
      setErrorMsg(message);
      setStatus("error");
    }
  }

  const isLoading = status === "loading";

  return (
    <section className="todays-task" aria-label="Today's task">
      <div className="todays-task__header">
        <span className="todays-task__label">📅 Today's Task — Day {task.day}</span>
        <span className="todays-task__date">{formattedDate}</span>
      </div>

      <h2 className="todays-task__title">{displayTitle}</h2>

      <div className="todays-task__meta">
        <span className="todays-task__meta-icon" aria-hidden="true">⏱</span>
        <span>{task.estimatedDuration}</span>
      </div>

      {task.recommendationReason && (
        <p className="todays-task__reason">{task.recommendationReason}</p>
      )}

      <div className="todays-task__actions">
        <button
          className="todays-task__btn todays-task__btn--progress"
          onClick={() => updateStatus("In Progress")}
          disabled={isLoading}
          aria-busy={isLoading}
        >
          {isLoading ? "Updating…" : "Mark as In Progress"}
        </button>
        <button
          className="todays-task__btn todays-task__btn--complete"
          onClick={() => updateStatus("Completed")}
          disabled={isLoading}
          aria-busy={isLoading}
        >
          {isLoading ? "Updating…" : "✓ Mark as Complete"}
        </button>
        <button
          className="todays-task__btn todays-task__btn--skip"
          onClick={() => updateStatus("Skipped")}
          disabled={isLoading}
          aria-busy={isLoading}
        >
          {isLoading ? "Updating…" : "Skip"}
        </button>
      </div>

      {status === "error" && errorMsg && (
        <p className="todays-task__error" role="alert">
          {errorMsg}
        </p>
      )}
    </section>
  );
}
