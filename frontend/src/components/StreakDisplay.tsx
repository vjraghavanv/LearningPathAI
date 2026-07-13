import "./StreakDisplay.css";

interface StreakDisplayProps {
  /** The current study streak in days. Accepts null or undefined for "no streak". */
  streak: number | null | undefined;
}

/**
 * Displays the user's current study streak (consecutive days with at least
 * one resource completion). Handles streak === 0, null, and undefined by
 * showing a motivational prompt to start a streak.
 */
export function StreakDisplay({ streak }: StreakDisplayProps) {
  const hasStreak = streak != null && streak > 0;
  const ariaLabel = hasStreak
    ? `Study streak: ${streak} day${streak === 1 ? "" : "s"}`
    : "No active study streak";

  return (
    <section className="streak-display" aria-label={ariaLabel}>
      <div className="streak-display__header">
        <h2 className="streak-display__title">🔥 Study Streak</h2>
      </div>
      <div className="streak-display__body">
        <span className="streak-display__icon" aria-hidden="true">🔥</span>
        {hasStreak ? (
          <div className="streak-display__active">
            <span className="streak-display__count">{streak}</span>
            <span className="streak-display__label">
              day{streak === 1 ? "" : "s"} in a row
            </span>
          </div>
        ) : (
          <div className="streak-display__inactive">
            <span className="streak-display__count streak-display__count--zero">
              0
            </span>
            <span className="streak-display__label">
              Start your streak today!
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
