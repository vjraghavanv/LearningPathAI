import "./PriorityResources.css";

export interface PriorityResource {
  resourceId: string;
  title: string;
  url: string;
  resourceType: string;
  difficulty: "Beginner" | "Intermediate" | "Advanced";
  learningStatus: string;
  aiMetadata: {
    priorityScore: number;
    summary?: string;
    skills?: string[];
    difficulty?: string;
    estimatedTime?: string;
    whyLearnNow?: string;
    recommendedWeek?: number;
  } | null;
}

interface PriorityResourcesProps {
  resources: PriorityResource[];
}

/** Maps difficulty to a CSS modifier class */
function difficultyClass(difficulty: string): string {
  switch (difficulty) {
    case "Beginner":
      return "priority-resources__difficulty--beginner";
    case "Advanced":
      return "priority-resources__difficulty--advanced";
    default:
      return "priority-resources__difficulty--intermediate";
  }
}

/**
 * Displays a sorted list of high-priority resources (descending priorityScore).
 * Shows title, resource type, difficulty, priority score, and a link.
 * Handles empty state gracefully.
 */
export function PriorityResources({ resources }: PriorityResourcesProps) {
  // Sort by priorityScore descending; resources without AI metadata sort last
  const sorted = [...resources].sort((a, b) => {
    const scoreA = a.aiMetadata?.priorityScore ?? -1;
    const scoreB = b.aiMetadata?.priorityScore ?? -1;
    return scoreB - scoreA;
  });

  const hasItems = sorted.length > 0;

  return (
    <section className="priority-resources" aria-label="Priority resources">
      <h2 className="priority-resources__title">🎯 Priority Resources</h2>
      {hasItems ? (
        <ul className="priority-resources__list" aria-label="Resource list">
          {sorted.map((resource) => {
            const score = resource.aiMetadata?.priorityScore;
            return (
              <li key={resource.resourceId} className="priority-resources__item">
                <div className="priority-resources__item-header">
                  <a
                    className="priority-resources__link"
                    href={resource.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Open resource: ${resource.title}`}
                  >
                    {resource.title}
                  </a>
                  {score != null && (
                    <span
                      className="priority-resources__score"
                      title="Priority score (0–100)"
                      aria-label={`Priority score: ${score}`}
                    >
                      {score}
                    </span>
                  )}
                </div>
                <div className="priority-resources__meta">
                  <span className="priority-resources__type">
                    {resource.resourceType}
                  </span>
                  <span
                    className={`priority-resources__difficulty ${difficultyClass(
                      resource.difficulty
                    )}`}
                  >
                    {resource.difficulty}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="priority-resources__empty">
          No priority resources available yet.
        </p>
      )}
    </section>
  );
}
