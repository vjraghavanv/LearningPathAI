import "./WeeklyProgressBar.css";

export interface WeeklyProgressEntry {
  day: string;
  completed: number;
  total: number;
}

interface WeeklyProgressBarProps {
  entries: WeeklyProgressEntry[] | null;
}

/**
 * Horizontal bar chart showing weekly learning progress.
 * Each bar's height is proportional to completed / total for that day.
 */
export function WeeklyProgressBar({ entries }: WeeklyProgressBarProps) {
  if (!entries || entries.length === 0) {
    return (
      <p className="weekly-progress__empty">No data yet</p>
    );
  }

  return (
    <div className="weekly-progress__bars" role="list" aria-label="Weekly progress">
      {entries.map((entry) => {
        const ratio =
          entry.total > 0
            ? Math.min(1, Math.max(0, entry.completed / entry.total))
            : 0;
        const heightPct = Math.round(ratio * 100);
        const label = `${entry.day}: ${entry.completed} of ${entry.total} completed`;

        return (
          <div key={entry.day} className="weekly-progress__col" role="listitem">
            <div
              className="weekly-progress__bar-track"
              title={label}
              aria-label={label}
            >
              <div
                className="weekly-progress__bar-fill"
                style={{ height: `${heightPct}%` }}
              />
            </div>
            <span className="weekly-progress__day">{entry.day}</span>
          </div>
        );
      })}
    </div>
  );
}
