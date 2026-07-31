import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorBanner } from "../components/ErrorBanner";
import { ResourceForm } from "../components/ResourceForm";
import {
  Difficulty,
  DIFFICULTIES,
  LEARNING_STATUSES,
  LearningStatus,
  Resource,
  ResourceFormData,
  ResourceType,
  RESOURCE_TYPES,
} from "../types/resource";
import "./ResourcesPage.css";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Converts comma-separated tag string into a trimmed array, omitting blanks */
function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Converts the form data into the API request body */
function formDataToPayload(data: ResourceFormData): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    title: data.title.trim(),
    url: data.url.trim(),
    resourceType: data.resourceType as ResourceType,
    learningStatus: data.learningStatus as LearningStatus,
  };
  if (data.difficulty) payload.difficulty = data.difficulty as Difficulty;
  if (data.estimatedDuration.trim()) payload.estimatedDuration = data.estimatedDuration.trim();
  if (data.technology.trim()) payload.technology = data.technology.trim();
  const tags = parseTags(data.tags);
  if (tags.length > 0) payload.tags = tags;
  return payload;
}

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

const STATUS_CLASSES: Record<LearningStatus, string> = {
  "Not Started": "resource-status--not-started",
  "In Progress": "resource-status--in-progress",
  Completed: "resource-status--completed",
  Skipped: "resource-status--skipped",
};

const STATUS_ICONS: Record<LearningStatus, string> = {
  "Not Started": "○",
  "In Progress": "◑",
  Completed: "✓",
  Skipped: "⊘",
};

function StatusBadge({ status }: { status: LearningStatus }) {
  const cls = STATUS_CLASSES[status] ?? "resource-status--not-started";
  const icon = STATUS_ICONS[status] ?? "○";
  return (
    <span className={`resource-status ${cls}`} aria-label={`Status: ${status}`}>
      <span className="resource-status__icon" aria-hidden="true">{icon}</span>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Difficulty badge helper
// ---------------------------------------------------------------------------

const DIFFICULTY_CLASSES: Record<Difficulty, string> = {
  Beginner: "resource-difficulty--beginner",
  Intermediate: "resource-difficulty--intermediate",
  Advanced: "resource-difficulty--advanced",
};

function DifficultyBadge({ difficulty }: { difficulty: Difficulty }) {
  const cls = DIFFICULTY_CLASSES[difficulty] ?? "";
  return <span className={`resource-difficulty ${cls}`}>{difficulty}</span>;
}

// ---------------------------------------------------------------------------
// ResourceCard — single resource row
// ---------------------------------------------------------------------------

interface ResourceCardProps {
  resource: Resource;
  onEdit: (resource: Resource) => void;
  onDelete: (resourceId: string) => void;
}

function ResourceCard({ resource, onEdit, onDelete }: ResourceCardProps) {
  return (
    <li className="resource-card" aria-label={`Resource: ${resource.title}`}>
      <div className="resource-card__main">
        <div className="resource-card__header">
          <a
            className="resource-card__title"
            href={resource.url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open ${resource.title} in new tab`}
          >
            {resource.title}
          </a>
          <div className="resource-card__badges">
            <StatusBadge status={resource.learningStatus} />
            {resource.difficulty && (
              <DifficultyBadge difficulty={resource.difficulty} />
            )}
          </div>
        </div>

        <div className="resource-card__meta">
          <span className="resource-card__type">{resource.resourceType}</span>
          {resource.technology && (
            <span className="resource-card__meta-item">
              🏷 {resource.technology}
            </span>
          )}
          {resource.estimatedDuration && (
            <span className="resource-card__meta-item">
              ⏱ {resource.estimatedDuration}
            </span>
          )}
        </div>

        {resource.tags && resource.tags.length > 0 && (
          <div className="resource-card__tags" aria-label="Tags">
            {resource.tags.map((tag) => (
              <span key={tag} className="resource-card__tag">
                {tag}
              </span>
            ))}
          </div>
        )}

        {resource.aiMetadata?.summary && (
          <p className="resource-card__summary">{resource.aiMetadata.summary}</p>
        )}
      </div>

      <div className="resource-card__actions">
        <button
          className="resource-card__btn resource-card__btn--edit"
          onClick={() => onEdit(resource)}
          aria-label={`Edit ${resource.title}`}
        >
          ✏ Edit
        </button>
        <button
          className="resource-card__btn resource-card__btn--delete"
          onClick={() => onDelete(resource.resourceId)}
          aria-label={`Delete ${resource.title}`}
        >
          🗑 Delete
        </button>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

interface DeleteConfirmProps {
  resourceTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
  error: string | null;
}

function DeleteConfirmDialog({
  resourceTitle,
  onConfirm,
  onCancel,
  deleting,
  error,
}: DeleteConfirmProps) {
  return (
    <div className="delete-confirm" role="alertdialog" aria-modal="true" aria-labelledby="delete-confirm-title">
      <p id="delete-confirm-title" className="delete-confirm__message">
        Delete <strong>{resourceTitle}</strong>? This cannot be undone.
      </p>
      {error && (
        <p className="delete-confirm__error" role="alert">
          {error}
        </p>
      )}
      <div className="delete-confirm__actions">
        <button
          className="resource-form__btn resource-form__btn--primary delete-confirm__btn--danger"
          onClick={onConfirm}
          disabled={deleting}
          aria-busy={deleting}
        >
          {deleting ? "Deleting…" : "Yes, delete"}
        </button>
        <button
          className="resource-form__btn resource-form__btn--secondary"
          onClick={onCancel}
          disabled={deleting}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type PageView = "list" | "add" | "edit";

export function ResourcesPage() {
  const { data, loading, error, execute, reset } = useApi<Resource[]>(
    useCallback(() => apiClient.get<Resource[]>("/resources"), [])
  );

  const [view, setView] = useState<PageView>("list");
  const [editingResource, setEditingResource] = useState<Resource | null>(null);

  // Delete state
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteInProgress, setDeleteInProgress] = useState(false);

  // Inline action error (for form submit failures)
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    execute();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Add resource ───────────────────────────────────────────────────────────
  async function handleAdd(formData: ResourceFormData) {
    setActionError(null);
    await apiClient.post<Resource>("/resources", formDataToPayload(formData));
    setView("list");
    await execute();
  }

  // ── Edit resource ──────────────────────────────────────────────────────────
  async function handleEdit(formData: ResourceFormData) {
    if (!editingResource) return;
    setActionError(null);
    try {
      const editId = editingResource.resourceId.replace(/^RESOURCE#/, "");
      await apiClient.put<Resource>(
        `/resources/${encodeURIComponent(editId)}`,
        formDataToPayload(formData)
      );
      setView("list");
      setEditingResource(null);
      await execute();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.toUserMessage()
          : "Failed to update resource. Please try again.";
      // Re-throw so ResourceForm displays the error inline
      throw new Error(message);
    }
  }

  // ── Delete resource ────────────────────────────────────────────────────────
  async function confirmDelete() {
    if (!deletingId) return;
    setDeleteInProgress(true);
    setDeleteError(null);
    try {
      const id = deletingId.replace(/^RESOURCE#/, "");
      await apiClient.delete(`/resources/${encodeURIComponent(id)}`);
      setDeletingId(null);
      await execute();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.toUserMessage()
          : "Failed to delete resource. Please try again.";
      setDeleteError(message);
    } finally {
      setDeleteInProgress(false);
    }
  }

  function openEdit(resource: Resource) {
    setEditingResource(resource);
    setActionError(null);
    setView("edit");
  }

  function openAdd() {
    setActionError(null);
    setView("add");
  }

  function cancelForm() {
    setView("list");
    setEditingResource(null);
    setActionError(null);
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading && data === null) return <LoadingSpinner label="Loading resources…" />;
  if (error && data === null) return <ErrorBanner message={error} onDismiss={reset} />;

  const resources = data ?? [];

  if (view === "add") {
    return (
      <div className="resources-page">
        <h1 className="resources-page__heading">Resources</h1>
        {actionError && <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />}
        <ResourceForm onSubmit={handleAdd} onCancel={cancelForm} />
      </div>
    );
  }

  if (view === "edit" && editingResource) {
    return (
      <div className="resources-page">
        <h1 className="resources-page__heading">Resources</h1>
        {actionError && <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />}
        <ResourceForm
          initialValues={editingResource}
          onSubmit={handleEdit}
          onCancel={cancelForm}
          isEditing
        />
      </div>
    );
  }

  return (
    <div className="resources-page">
      <div className="resources-page__top-row">
        <h1 className="resources-page__heading">Resources</h1>
        <button
          className="resources-page__add-btn"
          onClick={openAdd}
          aria-label="Add new resource"
        >
          + Add Resource
        </button>
      </div>

      {/* Non-blocking action errors (e.g. failed delete) */}
      {actionError && (
        <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />
      )}

      {/* Loading overlay for background refreshes */}
      {loading && data !== null && (
        <p className="resources-page__refreshing" aria-live="polite">
          Refreshing…
        </p>
      )}

      {/* Delete confirmation */}
      {deletingId !== null && (
        <DeleteConfirmDialog
          resourceTitle={
            resources.find((r) => r.resourceId === deletingId)?.title ??
            "this resource"
          }
          onConfirm={confirmDelete}
          onCancel={() => { setDeletingId(null); setDeleteError(null); }}
          deleting={deleteInProgress}
          error={deleteError}
        />
      )}

      {resources.length === 0 ? (
        <div className="resources-page__empty">
          <p>No resources yet. Add your first learning resource to get started.</p>
          <button className="resources-page__add-btn" onClick={openAdd}>
            + Add Resource
          </button>
        </div>
      ) : (
        <ul className="resources-page__list" aria-label="Resource list">
          {resources.map((resource) => (
            <ResourceCard
              key={resource.resourceId}
              resource={resource}
              onEdit={openEdit}
              onDelete={(id) => {
                setDeleteError(null);
                setDeletingId(id);
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Named exports for the search page to reuse
// ---------------------------------------------------------------------------
export { StatusBadge, DifficultyBadge, RESOURCE_TYPES, DIFFICULTIES, LEARNING_STATUSES };
