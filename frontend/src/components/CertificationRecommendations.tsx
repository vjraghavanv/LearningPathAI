import "./CertificationRecommendations.css";

interface CertificationRecommendationsProps {
  certifications: string[];
  projects: string[];
}

/**
 * Displays upcoming certification recommendations and recommended projects
 * from the active Learning_Plan. Both lists are string arrays from the plan.
 * Handles empty state for each section gracefully.
 */
export function CertificationRecommendations({
  certifications,
  projects,
}: CertificationRecommendationsProps) {
  const hasCerts = certifications.length > 0;
  const hasProjects = projects.length > 0;

  return (
    <section
      className="cert-recommendations"
      aria-label="Certifications and projects"
    >
      {/* Certifications */}
      <div className="cert-recommendations__section">
        <h2 className="cert-recommendations__title">
          🏅 Certification Recommendations
        </h2>
        {hasCerts ? (
          <ul
            className="cert-recommendations__list"
            aria-label="Certification list"
          >
            {certifications.map((cert, index) => (
              <li key={index} className="cert-recommendations__item cert-recommendations__item--cert">
                <span
                  className="cert-recommendations__icon"
                  aria-hidden="true"
                >
                  🎓
                </span>
                <span className="cert-recommendations__text">{cert}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="cert-recommendations__empty">
            No certification recommendations yet.
          </p>
        )}
      </div>

      {/* Recommended Projects */}
      <div className="cert-recommendations__section cert-recommendations__section--projects">
        <h2 className="cert-recommendations__title">🚀 Recommended Projects</h2>
        {hasProjects ? (
          <ul
            className="cert-recommendations__list"
            aria-label="Project list"
          >
            {projects.map((project, index) => (
              <li key={index} className="cert-recommendations__item cert-recommendations__item--project">
                <span
                  className="cert-recommendations__icon"
                  aria-hidden="true"
                >
                  💡
                </span>
                <span className="cert-recommendations__text">{project}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="cert-recommendations__empty">
            No project recommendations yet.
          </p>
        )}
      </div>
    </section>
  );
}
