import { useState } from "react";
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
import "./ResourceForm.css";

interface ResourceFormProps {
  /** Pre-populated values when editing an existing resource */
  initialValues?: Partial<Resource>;
  onSubmit: (data: ResourceFormData) => Promise<void>;
  onCancel: () => void;
  isEditing?: boolean;
}

type FieldErrors = Partial<Record<keyof ResourceFormData, string>>;

/** Validate the form and return a map of error messages (empty map = valid). */
function validate(values: ResourceFormData): FieldErrors {
  const errors: FieldErrors = {};

  if (!values.title.trim()) {
    errors.title = "Title is required.";
  }

  if (!values.url.trim()) {
    errors.url = "URL is required.";
  } else {
    try {
      new URL(values.url.trim());
    } catch {
      errors.url = "Please enter a valid URL (e.g. https://example.com).";
    }
  }

  if (!values.resourceType) {
    errors.resourceType = "Resource type is required.";
  } else if (!(RESOURCE_TYPES as string[]).includes(values.resourceType)) {
    errors.resourceType = "Please select a valid resource type.";
  }

  if (values.difficulty && !(DIFFICULTIES as string[]).includes(values.difficulty)) {
    errors.difficulty = "Please select a valid difficulty level.";
  }

  return errors;
}

/**
 * A controlled form for creating or editing a learning resource.
 * Performs client-side validation before calling onSubmit.
 */
export function ResourceForm({
  initialValues,
  onSubmit,
  onCancel,
  isEditing = false,
}: ResourceFormProps) {
  const [values, setValues] = useState<ResourceFormData>({
    title: initialValues?.title ?? "",
    url: initialValues?.url ?? "",
    resourceType: (initialValues?.resourceType as ResourceType | "") ?? "",
    estimatedDuration: initialValues?.estimatedDuration ?? "",
    difficulty: (initialValues?.difficulty as Difficulty | "") ?? "",
    tags: initialValues?.tags?.join(", ") ?? "",
    technology: initialValues?.technology ?? "",
    learningStatus:
      (initialValues?.learningStatus as LearningStatus) ?? "Not Started",
  });

  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) {
    const { name, value } = e.target;
    setValues((prev) => ({ ...prev, [name]: value }));
    // Clear the field-level error as the user types
    if (errors[name as keyof ResourceFormData]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);

    const fieldErrors = validate(values);
    if (Object.keys(fieldErrors).length > 0) {
      setErrors(fieldErrors);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Something went wrong. Please try again.";
      setSubmitError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="resource-form" onSubmit={handleSubmit} noValidate aria-label={isEditing ? "Edit resource" : "Add resource"}>
      <h2 className="resource-form__title">
        {isEditing ? "Edit Resource" : "Add Resource"}
      </h2>

      {/* Title */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-title">
          Title <span className="resource-form__required" aria-hidden="true">*</span>
        </label>
        <input
          id="rf-title"
          className={`resource-form__input${errors.title ? " resource-form__input--error" : ""}`}
          type="text"
          name="title"
          value={values.title}
          onChange={handleChange}
          placeholder="e.g. AWS IAM Deep Dive"
          aria-required="true"
          aria-describedby={errors.title ? "rf-title-err" : undefined}
          disabled={submitting}
        />
        {errors.title && (
          <span id="rf-title-err" className="resource-form__error" role="alert">
            {errors.title}
          </span>
        )}
      </div>

      {/* URL */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-url">
          URL <span className="resource-form__required" aria-hidden="true">*</span>
        </label>
        <input
          id="rf-url"
          className={`resource-form__input${errors.url ? " resource-form__input--error" : ""}`}
          type="url"
          name="url"
          value={values.url}
          onChange={handleChange}
          placeholder="https://example.com/article"
          aria-required="true"
          aria-describedby={errors.url ? "rf-url-err" : undefined}
          disabled={submitting}
        />
        {errors.url && (
          <span id="rf-url-err" className="resource-form__error" role="alert">
            {errors.url}
          </span>
        )}
      </div>

      {/* Resource Type */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-type">
          Resource Type <span className="resource-form__required" aria-hidden="true">*</span>
        </label>
        <select
          id="rf-type"
          className={`resource-form__select${errors.resourceType ? " resource-form__input--error" : ""}`}
          name="resourceType"
          value={values.resourceType}
          onChange={handleChange}
          aria-required="true"
          aria-describedby={errors.resourceType ? "rf-type-err" : undefined}
          disabled={submitting}
        >
          <option value="">— Select type —</option>
          {RESOURCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        {errors.resourceType && (
          <span id="rf-type-err" className="resource-form__error" role="alert">
            {errors.resourceType}
          </span>
        )}
      </div>

      {/* Difficulty */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-difficulty">
          Difficulty
        </label>
        <select
          id="rf-difficulty"
          className={`resource-form__select${errors.difficulty ? " resource-form__input--error" : ""}`}
          name="difficulty"
          value={values.difficulty}
          onChange={handleChange}
          aria-describedby={errors.difficulty ? "rf-difficulty-err" : undefined}
          disabled={submitting}
        >
          <option value="">— Select difficulty —</option>
          {DIFFICULTIES.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        {errors.difficulty && (
          <span id="rf-difficulty-err" className="resource-form__error" role="alert">
            {errors.difficulty}
          </span>
        )}
      </div>

      {/* Learning Status */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-status">
          Learning Status
        </label>
        <select
          id="rf-status"
          className="resource-form__select"
          name="learningStatus"
          value={values.learningStatus}
          onChange={handleChange}
          disabled={submitting}
        >
          {LEARNING_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Technology */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-technology">
          Technology
        </label>
        <input
          id="rf-technology"
          className="resource-form__input"
          type="text"
          name="technology"
          value={values.technology}
          onChange={handleChange}
          placeholder="e.g. AWS, Kubernetes, Python"
          disabled={submitting}
        />
      </div>

      {/* Estimated Duration */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-duration">
          Estimated Duration
        </label>
        <input
          id="rf-duration"
          className="resource-form__input"
          type="text"
          name="estimatedDuration"
          value={values.estimatedDuration}
          onChange={handleChange}
          placeholder="e.g. 2 hours, 30 minutes"
          disabled={submitting}
        />
      </div>

      {/* Tags */}
      <div className="resource-form__field">
        <label className="resource-form__label" htmlFor="rf-tags">
          Tags
          <span className="resource-form__hint"> (comma-separated)</span>
        </label>
        <input
          id="rf-tags"
          className="resource-form__input"
          type="text"
          name="tags"
          value={values.tags}
          onChange={handleChange}
          placeholder="e.g. iam, security, aws"
          disabled={submitting}
        />
      </div>

      {/* Form-level error */}
      {submitError && (
        <p className="resource-form__submit-error" role="alert">
          {submitError}
        </p>
      )}

      {/* Actions */}
      <div className="resource-form__actions">
        <button
          type="submit"
          className="resource-form__btn resource-form__btn--primary"
          disabled={submitting}
          aria-busy={submitting}
        >
          {submitting ? "Saving…" : isEditing ? "Save Changes" : "Add Resource"}
        </button>
        <button
          type="button"
          className="resource-form__btn resource-form__btn--secondary"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
