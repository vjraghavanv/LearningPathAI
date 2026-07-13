import "./LearningTimeline.css";

interface LearningTimelineProps {
  roadmap: string[] | null;
}

/**
 * Renders a vertical timeline list for the weekly learning roadmap.
 * Each item shows a numbered circle, a connecting line, and the roadmap step text.
 */
export function LearningTimeline({ roadmap }: LearningTimelineProps) {
  const hasItems = roadmap && roadmap.length > 0;

  return (
    <section className="learning-timeline" aria-label="Learning roadmap">
      <h2 className="learning-timeline__title">📍 Learning Roadmap</h2>
      {hasItems ? (
        <ol className="learning-timeline__list" aria-label="Roadmap steps">
          {roadmap.map((step, index) => (
            <li key={index} className="learning-timeline__item">
              <span
                className="learning-timeline__step-indicator"
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <div className="learning-timeline__step-content">
                <p className="learning-timeline__step-text">{step}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="learning-timeline__empty">No roadmap available yet</p>
      )}
    </section>
  );
}
