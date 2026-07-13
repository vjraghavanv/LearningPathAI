import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorBanner } from "../components/ErrorBanner";
import "./LearningPlanPage.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DailyScheduleEntry {
  day: number;
  date?: string;
  resourceId: string;
  estimatedDuration: string;
  recommendationReason: string;
}

export interface LearningPlan {
  dailySchedule: DailyScheduleEntry[];
  weeklyRoadmap: string[];
  recommendedProjects: string[];
  certificationRecommendations: string[];
  estimatedCompletionTimeline: string;
  generatedAt?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO date string as a short human-readable day label */
function formatDate(isoDate?: string): string {
  if (!isoDate) return "";
  try {
    return new Date(isoDate).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  } catch {
    return isoDate;
  }
}

/** Check whether a plan entry's date corresponds to today */
function isToday(isoDate?: string): boolean {
  if (!isoDate) return false;
  const today = new Date().toDateString();
  try {
    return new Date(isoDate).toDateString() === today;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// DailyScheduleCard
// ---------------------------------------------------------------------------

interface DailyScheduleCardProps {
  entry: DailyScheduleEntry;
}

function DailyScheduleCard({ entry }: DailyScheduleCardProps) {
  const today = isToday(entry.date);

  return (
    <li
      className={`plan-day-card${today ? " plan-day-card--today" : ""}`}
      aria-label={`Day ${entry.day}${today ? " — Today" : ""}`}
    >
      <div className="plan-day-card__header">
        <div className="plan-day-card__day-badge" aria-hidden="true">
          Day {entry.day}
        </div>
        {today && (
          <span className="plan-day-card__today-badge" aria-label="Today">
            📅 Today
          </span>
        )}
        {entry.date && !today && (
          <span className="plan-day-card__date">{formatDate(entry.date)}</span>
        )}
      </div>

      <div className="plan-day-card__body">
        <p className="plan-day-card__resource-id" aria-label="Resource">
          <span className="plan-day-card__icon" aria-hidden="true">📖</span>
          <span className="plan-day-card__resource-label">Resource:</span>{" "}
          <code className="plan-day-card__resource-code">{entry.resourceId}</code>
        </p>

        {entry.estimatedDuration && (
          <p className="plan-day-card__duration">
            <span className="plan-day-card__icon" aria-hidden="true">⏱</span>
            {entry.estimatedDuration}
          </p>
        )}

        {entry.recommendationReason && (
          <blockquote className="plan-day-card__reason">
            <span className="plan-day-card__reason-icon" aria-hidden="true">💡</span>
            {entry.recommendationReason}
          </blockquote>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// WeeklyRoadmap
// ---------------------------------------------------------------------------

function WeeklyRoadmapSection({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="plan-section" aria-labelledby="plan-roadmap-heading">
      <h2 id="plan-roadmap-heading" className="plan-section__heading">
        📍 Weekly Roadmap
      </h2>
      <ol className="plan-roadmap__list">
        {items.map((item, i) => (
          <li key={i} className="plan-roadmap__item">{item}</li>
        ))}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------------------
// RecommendationsList
// ---------------------------------------------------------------------------

function RecommendationsList({
  heading,
  icon,
  items,
  id,
}: {
  heading: string;
  icon: string;
  items: string[];
  id: string;
}) {
  if (items.length === 0) return null;
  return (
    <section className="plan-section" aria-labelledby={id}>
      <h2 id={id} className="plan-section__heading">
        {icon} {heading}
      </h2>
      <ul className="plan-recommendations__list">
        {items.map((item, i) => (
          <li key={i} className="plan-recommendations__item">{item}</li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// GeneratePlanButton
// ---------------------------------------------------------------------------

interface GeneratePlanButtonProps {
  onGenerate: () => Promise<void>;
  generating: boolean;
  error: string | null;
}

function GeneratePlanButton({ onGenerate, generating, error }: GeneratePlanButtonProps) {
  return (
    <div className="plan-generate">
      {error && (
        <p className="plan-generate__error" role="alert">
          {error}
        </p>
      )}
      <button
        className="plan-generate__btn"
        onClick={onGenerate}
        disabled={generating}
        aria-busy={generating}
      >
        {generating ? "Generating plan…" : "✨ Generate Learning Plan"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LearningPlanPage
// ---------------------------------------------------------------------------

export function LearningPlanPage() {
  const { data, loading, error, execute, reset } = useApi<LearningPlan>(
    useCallback(() => apiClient.get<LearningPlan>("/learning-plan"), [])
  );

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  useEffect(() => {
    execute();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setGenerateError(null);
    setGenerating(true);
    try {
      await apiClient.post("/learning-plan", {});
      await execute();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.toUserMessage()
          : "Failed to generate plan. Please try again.";
      setGenerateError(message);
    } finally {
      setGenerating(false);
    }
  }

  if (loading && data === null) return <LoadingSpinner label="Loading learning plan…" />;
  if (error && data === null) return <ErrorBanner message={error} onDismiss={reset} />;

  return (
    <div className="learning-plan-page">
      <div className="learning-plan-page__top-row">
        <h1 className="learning-plan-page__heading">Learning Plan</h1>
        <GeneratePlanButton
          onGenerate={handleGenerate}
          generating={generating}
          error={generateError}
        />
      </div>

      {!data ? (
        <div className="learning-plan-page__empty">
          <p className="learning-plan-page__empty-text">
            No learning plan yet.{" "}
            <Link to="/career" className="learning-plan-page__link">
              Set up your career goal
            </Link>{" "}
            first, then generate a plan above.
          </p>
        </div>
      ) : (
        <>
          {/* Timeline summary */}
          {data.estimatedCompletionTimeline && (
            <div className="plan-timeline-banner">
              <span className="plan-timeline-banner__icon" aria-hidden="true">🏁</span>
              <span>
                <strong>Estimated completion:</strong>{" "}
                {data.estimatedCompletionTimeline}
              </span>
            </div>
          )}

          {/* Daily schedule */}
          <section className="plan-section" aria-labelledby="plan-schedule-heading">
            <h2 id="plan-schedule-heading" className="plan-section__heading">
              🗓️ Daily Schedule
            </h2>
            {data.dailySchedule.length === 0 ? (
              <p className="plan-section__empty">No daily entries in this plan.</p>
            ) : (
              <ol className="plan-schedule__list" aria-label="Daily schedule">
                {data.dailySchedule.map((entry) => (
                  <DailyScheduleCard key={entry.day} entry={entry} />
                ))}
              </ol>
            )}
          </section>

          <WeeklyRoadmapSection items={data.weeklyRoadmap ?? []} />

          <RecommendationsList
            id="plan-projects-heading"
            heading="Recommended Projects"
            icon="🛠️"
            items={data.recommendedProjects ?? []}
          />

          <RecommendationsList
            id="plan-certs-heading"
            heading="Certification Recommendations"
            icon="🎓"
            items={data.certificationRecommendations ?? []}
          />

          {data.generatedAt && (
            <p className="plan-generated-at">
              Last generated:{" "}
              {new Date(data.generatedAt).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              })}
            </p>
          )}
        </>
      )}
    </div>
  );
}
