import { useState } from "react";
import { apiClient } from "../api/client";
import { Resource, ResourceType, Difficulty, RESOURCE_TYPES, DIFFICULTIES } from "../types/resource";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge, DifficultyBadge } from "./ResourcesPage";
import "./SearchPage.css";

interface SearchFilters {
  technology: string;
  difficulty: Difficulty | "";
  resourceType: ResourceType | "";
  skillTag: string;
  certificationTag: string;
  tag: string;
}

const EMPTY_FILTERS: SearchFilters = {
  technology: "",
  difficulty: "",
  resourceType: "",
  skillTag: "",
  certificationTag: "",
  tag: "",
};

function SearchResultCard({ resource }: { resource: Resource }) {
  return (
    <li className="search-result-card" aria-label={`Resource: ${resource.title}`}>
      <div className="search-result-card__header">
        <a
          className="search-result-card__title"
          href={resource.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Open ${resource.title} in new tab`}
        >
          {resource.title}
        </a>
        <div className="search-result-card__badges">
          <StatusBadge status={resource.learningStatus} />
          {resource.difficulty && (
            <DifficultyBadge difficulty={resource.difficulty} />
          )}
        </div>
      </div>
      <div className="search-result-card__meta">
        <span>{resource.resourceType}</span>
        {resource.technology && <span>&#127991; {resource.technology}</span>}
        {resource.estimatedDuration && <span>&#9201; {resource.estimatedDuration}</span>}
      </div>
      {resource.aiMetadata?.summary && (
        <p className="search-result-card__summary">{resource.aiMetadata.summary}</p>
      )}
    </li>
  );
}

export function SearchPage() {
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [results, setResults] = useState<Resource[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    if (filters.technology.trim()) params.set("technology", filters.technology.trim());
    if (filters.difficulty) params.set("difficulty", filters.difficulty);
    if (filters.resourceType) params.set("resourceType", filters.resourceType);
    if (filters.skillTag.trim()) params.set("skillTag", filters.skillTag.trim());
    if (filters.certificationTag.trim()) params.set("certificationTag", filters.certificationTag.trim());
    if (filters.tag.trim()) params.set("tag", filters.tag.trim());

    const queryString = params.toString();
    const path = queryString ? `/search?${queryString}` : "/search";

    try {
      const data = await apiClient.get<Resource[]>(path);
      setResults(data ?? []);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed. Please try again.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setFilters(EMPTY_FILTERS);
    setResults(null);
    setError(null);
    setSearched(false);
  }

  function handleFilterChange(field: keyof SearchFilters, value: string) {
    setFilters((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <div className="search-page">
      <h1 className="search-page__heading">Search Resources</h1>

      <form className="search-page__form" onSubmit={handleSearch} aria-label="Search filters">
        <div className="search-page__filters">
          <div className="search-page__field">
            <label className="search-page__label" htmlFor="search-technology">
              Technology
            </label>
            <input
              id="search-technology"
              className="search-page__input"
              type="text"
              placeholder="e.g. AWS, Docker"
              value={filters.technology}
              onChange={(e) => handleFilterChange("technology", e.target.value)}
              aria-label="Technology"
            />
          </div>

          <div className="search-page__field">
            <label className="search-page__label" htmlFor="search-difficulty">
              Difficulty
            </label>
            <select
              id="search-difficulty"
              className="search-page__select"
              value={filters.difficulty}
              onChange={(e) => handleFilterChange("difficulty", e.target.value as Difficulty | "")}
              aria-label="Difficulty"
            >
              <option value="">Any difficulty</option>
              {DIFFICULTIES.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          <div className="search-page__field">
            <label className="search-page__label" htmlFor="search-resource-type">
              Resource Type
            </label>
            <select
              id="search-resource-type"
              className="search-page__select"
              value={filters.resourceType}
              onChange={(e) => handleFilterChange("resourceType", e.target.value as ResourceType | "")}
              aria-label="Resource Type"
            >
              <option value="">Any type</option>
              {RESOURCE_TYPES.map((rt) => (
                <option key={rt} value={rt}>
                  {rt}
                </option>
              ))}
            </select>
          </div>

          <div className="search-page__field">
            <label className="search-page__label" htmlFor="search-skill-tag">
              Skill Tag
            </label>
            <input
              id="search-skill-tag"
              className="search-page__input"
              type="text"
              placeholder="e.g. IAM, EC2"
              value={filters.skillTag}
              onChange={(e) => handleFilterChange("skillTag", e.target.value)}
              aria-label="Skill Tag"
            />
          </div>

          <div className="search-page__field">
            <label className="search-page__label" htmlFor="search-cert-tag">
              Certification Tag
            </label>
            <input
              id="search-cert-tag"
              className="search-page__input"
              type="text"
              placeholder="e.g. AWS SAA-C03"
              value={filters.certificationTag}
              onChange={(e) => handleFilterChange("certificationTag", e.target.value)}
              aria-label="Certification Tag"
            />
          </div>

          <div className="search-page__field">
            <label className="search-page__label" htmlFor="search-tag">
              Tag
            </label>
            <input
              id="search-tag"
              className="search-page__input"
              type="text"
              placeholder="e.g. security"
              value={filters.tag}
              onChange={(e) => handleFilterChange("tag", e.target.value)}
              aria-label="Tag"
            />
          </div>
        </div>

        <div className="search-page__actions">
          <button
            type="submit"
            className="search-page__btn search-page__btn--primary"
            disabled={loading}
          >
            {loading ? "Searching..." : "Search"}
          </button>
          <button
            type="button"
            className="search-page__btn search-page__btn--secondary"
            onClick={handleClear}
          >
            Clear Filters
          </button>
        </div>
      </form>

      {loading && <LoadingSpinner label="Searching..." />}

      {error && !loading && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}

      {!loading && results !== null && (
        <>
          {results.length === 0 ? (
            <p className="search-page__result-count" role="status">
              No resources match your filters. Try broadening your search.
            </p>
          ) : (
            <>
              <p className="search-page__result-count" role="status">
                {results.length} resource{results.length !== 1 ? "s" : ""} found
              </p>
              <ul className="search-page__list" aria-label="Search results">
                {results.map((resource) => (
                  <SearchResultCard key={resource.resourceId} resource={resource} />
                ))}
              </ul>
            </>
          )}
        </>
      )}

      {!loading && !searched && results === null && !error && (
        <p style={{ color: "var(--color-text-secondary, #64748b)" }}>
          Use the filters above to search your resource library.
        </p>
      )}
    </div>
  );
}
