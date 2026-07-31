import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorBanner } from "../components/ErrorBanner";
import "./CareerGoalPage.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SkillLevel = "Beginner" | "Intermediate" | "Advanced";
export type LearningPace = "Slow" | "Moderate" | "Fast";

export interface CareerGoalProfile {
  careerGoal: string;
  currentSkillLevel: SkillLevel;
  weeklyStudyHours: number;
  targetCompletionDate?: string | null;
  preferredLearningPace: LearningPace;
  createdAt?: string;
  updatedAt?: string;
}

interface CareerGoalFormData {
  careerGoal: string;
  customCareerGoal: string;
  currentSkillLevel: SkillLevel | "";
  weeklyStudyHours: string;
  targetCompletionDate: string;
  preferredLearningPace: LearningPace | "";
}

type FieldErrors = Partial<Record<keyof CareerGoalFormData, string>>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PREDEFINED_GOALS = [
  "Become AWS Cloud Engineer",
  "Become DevOps Engineer",
  "Become AI Engineer",
  "Crack AWS SAA Certification",
  "Become Playwright Automation Expert",
  "__custom__",
] as const;

const PREDEFINED_GOAL_LABELS: Record<string, string> = {
  "Become AWS Cloud Engineer": "Become AWS Cloud Engineer",
  "Become DevOps Engineer": "Become DevOps Engineer",
  "Become AI Engineer": "Become AI Engineer",
  "Crack AWS SAA Certification": "Crack AWS SAA Certification",
  "Become Playwright Automation Expert": "Become Playwright Automation Expert",
  "__custom__": "Other (custom goal…)",
};

const SKILL_LEVELS: SkillLevel[] = ["Beginner", "Intermediate", "Advanced"];
const LEARNING_PACES: LearningPace[] = ["Slow", "Moderate", "Fast"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function validate(values: CareerGoalFormData): FieldErrors {
  const errors: FieldErrors = {};

  const effectiveGoal =
    values.careerGoal === "__custom__"
      ? values.customCareerGoal.trim()
      : values.careerGoal.trim();

  if (!effectiveGoal) {
    errors.careerGoal = "Career goal is required.";
  } else if (values.careerGoal === "__custom__" && effectiveGoal.length > 200) {
    errors.customCareerGoal = "Career goal must be 200 characters or fewer.";
  }

  if (!values.currentSkillLevel) {
    errors.currentSkillLevel = "Skill level is required.";
  }

  const hours = Number(values.weeklyStudyHours);
  if (!values.weeklyStudyHours.trim()) {
    errors.weeklyStudyHours = "Weekly study hours is required.";
  } else if (!Number.isInteger(hours) || hours < 1 || hours > 168) {
    errors.weeklyStudyHours = "Enter a whole number between 1 and 168.";
  }

  if (!values.preferredLearningPace) {
    errors.preferredLearningPace = "Learning pace is required.";
  }

  return errors;
}

function profileToFormData(profile: CareerGoalProfile): CareerGoalFormData {
  const isPredefined = (PREDEFINED_GOALS as readonly string[]).includes(profile.careerGoal) &&
    profile.careerGoal !== "__custom__";
  return {
    careerGoal: isPredefined ? profile.careerGoal : "__custom__",
    customCareerGoal: isPredefined ? "" : profile.careerGoal,
    currentSkillLevel: profile.currentSkillLevel,
    weeklyStudyHours: String(profile.weeklyStudyHours),
    targetCompletionDate: profile.targetCompletionDate ?? "",
    preferredLearningPace: profile.preferredLearningPace,
  };
}

function formDataToPayload(values: CareerGoalFormData): Record<string, unknown> {
  const careerGoal =
    values.careerGoal === "__custom__"
      ? values.customCareerGoal.trim()
      : values.careerGoal;
  const payload: Record<string, unknown> = {
    careerGoal,
    currentSkillLevel: values.currentSkillLevel,
    weeklyStudyHours: Number(values.weeklyStudyHours),
    preferredLearningPace: values.preferredLearningPace,
  };
  if (values.targetCompletionDate.trim()) {
    payload.targetCompletionDate = values.targetCompletionDate.trim();
  }
  return payload;
}

// ---------------------------------------------------------------------------
// CareerGoalForm
// ---------------------------------------------------------------------------

interface CareerGoalFormProps {
  initialValues?: CareerGoalProfile | null;
  onSubmit: (data: CareerGoalFormData) => Promise<void>;
  isEditing?: boolean;
}

function CareerGoalForm({ initialValues, onSubmit, isEditing = false }: CareerGoalFormProps) {
  const [values, setValues] = useState<CareerGoalFormData>(() =>
    initialValues
      ? profileToFormData(initialValues)
      : {
          careerGoal: "",
          customCareerGoal: "",
          currentSkillLevel: "",
          weeklyStudyHours: "",
          targetCompletionDate: "",
          preferredLearningPace: "",
        }
  );
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) {
    const { name, value } = e.target;
    setValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: undefined }));
    setSuccess(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setSuccess(false);

    const fieldErrors = validate(values);
    if (Object.keys(fieldErrors).length > 0) {
      setErrors(fieldErrors);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(values);
      setSuccess(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Something went wrong. Please try again.";
      setSubmitError(message);
    } finally {
      setSubmitting(false);
    }
  }

  const customGoalLength = values.customCareerGoal.length;

  return (
    <form
      className="career-goal-form"
      onSubmit={handleSubmit}
      noValidate
      aria-label={isEditing ? "Update career goal" : "Set up career goal"}
    >
      <h2 className="career-goal-form__title">
        {isEditing ? "Update Your Career Goal" : "Set Up Your Career Goal"}
      </h2>
      <p className="career-goal-form__subtitle">
        Tell us about your career goal and study availability so we can build
        a personalized learning roadmap for you.
      </p>

      {/* Career Goal */}
      <div className="career-goal-form__field">
        <label className="career-goal-form__label" htmlFor="cg-goal">
          Career Goal <span className="career-goal-form__required" aria-hidden="true">*</span>
        </label>
        <select
          id="cg-goal"
          className={`career-goal-form__select${errors.careerGoal ? " career-goal-form__input--error" : ""}`}
          name="careerGoal"
          value={values.careerGoal}
          onChange={handleChange}
          aria-required="true"
          aria-describedby={errors.careerGoal ? "cg-goal-err" : undefined}
          disabled={submitting}
        >
          <option value="">— Select a goal —</option>
          {PREDEFINED_GOALS.map((g) => (
            <option key={g} value={g}>
              {PREDEFINED_GOAL_LABELS[g]}
            </option>
          ))}
        </select>
        {errors.careerGoal && (
          <span id="cg-goal-err" className="career-goal-form__error" role="alert">
            {errors.careerGoal}
          </span>
        )}
      </div>

      {/* Custom goal text area — shown only when "Other" is selected */}
      {values.careerGoal === "__custom__" && (
        <div className="career-goal-form__field">
          <label className="career-goal-form__label" htmlFor="cg-custom">
            Describe your goal{" "}
            <span className="career-goal-form__required" aria-hidden="true">*</span>
          </label>
          <textarea
            id="cg-custom"
            className={`career-goal-form__textarea${errors.customCareerGoal ? " career-goal-form__input--error" : ""}`}
            name="customCareerGoal"
            value={values.customCareerGoal}
            onChange={handleChange}
            placeholder="e.g. Become a full-stack engineer specialising in cloud-native apps"
            maxLength={200}
            rows={3}
            aria-required="true"
            aria-describedby={errors.customCareerGoal ? "cg-custom-err" : "cg-custom-hint"}
            disabled={submitting}
          />
          <span id="cg-custom-hint" className="career-goal-form__char-count">
            {customGoalLength}/200
          </span>
          {errors.customCareerGoal && (
            <span id="cg-custom-err" className="career-goal-form__error" role="alert">
              {errors.customCareerGoal}
            </span>
          )}
        </div>
      )}

      {/* Current Skill Level */}
      <div className="career-goal-form__field">
        <label className="career-goal-form__label" htmlFor="cg-skill">
          Current Skill Level{" "}
          <span className="career-goal-form__required" aria-hidden="true">*</span>
        </label>
        <select
          id="cg-skill"
          className={`career-goal-form__select${errors.currentSkillLevel ? " career-goal-form__input--error" : ""}`}
          name="currentSkillLevel"
          value={values.currentSkillLevel}
          onChange={handleChange}
          aria-required="true"
          aria-describedby={errors.currentSkillLevel ? "cg-skill-err" : undefined}
          disabled={submitting}
        >
          <option value="">— Select skill level —</option>
          {SKILL_LEVELS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {errors.currentSkillLevel && (
          <span id="cg-skill-err" className="career-goal-form__error" role="alert">
            {errors.currentSkillLevel}
          </span>
        )}
      </div>

      {/* Weekly Study Hours */}
      <div className="career-goal-form__field">
        <label className="career-goal-form__label" htmlFor="cg-hours">
          Weekly Study Hours{" "}
          <span className="career-goal-form__required" aria-hidden="true">*</span>
        </label>
        <input
          id="cg-hours"
          className={`career-goal-form__input${errors.weeklyStudyHours ? " career-goal-form__input--error" : ""}`}
          type="number"
          name="weeklyStudyHours"
          value={values.weeklyStudyHours}
          onChange={handleChange}
          placeholder="e.g. 10"
          min={1}
          max={168}
          step={1}
          aria-required="true"
          aria-describedby={
            errors.weeklyStudyHours ? "cg-hours-err" : "cg-hours-hint"
          }
          disabled={submitting}
        />
        <span id="cg-hours-hint" className="career-goal-form__hint">
          Enter a whole number between 1 and 168
        </span>
        {errors.weeklyStudyHours && (
          <span id="cg-hours-err" className="career-goal-form__error" role="alert">
            {errors.weeklyStudyHours}
          </span>
        )}
      </div>

      {/* Preferred Learning Pace */}
      <div className="career-goal-form__field">
        <label className="career-goal-form__label" htmlFor="cg-pace">
          Preferred Learning Pace{" "}
          <span className="career-goal-form__required" aria-hidden="true">*</span>
        </label>
        <select
          id="cg-pace"
          className={`career-goal-form__select${errors.preferredLearningPace ? " career-goal-form__input--error" : ""}`}
          name="preferredLearningPace"
          value={values.preferredLearningPace}
          onChange={handleChange}
          aria-required="true"
          aria-describedby={errors.preferredLearningPace ? "cg-pace-err" : undefined}
          disabled={submitting}
        >
          <option value="">— Select pace —</option>
          {LEARNING_PACES.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        {errors.preferredLearningPace && (
          <span id="cg-pace-err" className="career-goal-form__error" role="alert">
            {errors.preferredLearningPace}
          </span>
        )}
      </div>

      {/* Target Completion Date (optional) */}
      <div className="career-goal-form__field">
        <label className="career-goal-form__label" htmlFor="cg-date">
          Target Completion Date
          <span className="career-goal-form__optional"> (optional)</span>
        </label>
        <input
          id="cg-date"
          className="career-goal-form__input"
          type="date"
          name="targetCompletionDate"
          value={values.targetCompletionDate}
          onChange={handleChange}
          disabled={submitting}
        />
      </div>

      {/* Form-level error */}
      {submitError && (
        <p className="career-goal-form__submit-error" role="alert">
          {submitError}
        </p>
      )}

      {/* Success message */}
      {success && (
        <p className="career-goal-form__success" role="status">
          {isEditing
            ? "Career goal updated. Your learning plan will regenerate shortly."
            : "Career goal saved. Generating your personalized learning plan…"}
        </p>
      )}

      <div className="career-goal-form__actions">
        <button
          type="submit"
          className="career-goal-form__btn career-goal-form__btn--primary"
          disabled={submitting}
          aria-busy={submitting}
        >
          {submitting
            ? "Saving…"
            : isEditing
            ? "Update Goal"
            : "Save & Generate Plan"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// CareerGoalPage
// ---------------------------------------------------------------------------

export function CareerGoalPage() {
  const navigate = useNavigate();
  const { data, loading, error, execute, reset } = useApi<CareerGoalProfile>(
    useCallback(async () => {
      try {
        return await apiClient.get<CareerGoalProfile>("/career-goal");
      } catch (err) {
        if (err instanceof ApiError && err.statusCode === 404) return null as unknown as CareerGoalProfile;
        throw err;
      }
    }, [])
  );

  useEffect(() => {
    execute();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(formData: CareerGoalFormData) {
    const payload = formDataToPayload(formData);
    try {
      if (data) {
        await apiClient.put<CareerGoalProfile>("/career-goal", payload);
      } else {
        await apiClient.post<CareerGoalProfile>("/career-goal", payload);
      }
      // Refresh profile state
      await execute();
      // Navigate to plan page after a short delay so the success message is visible
      setTimeout(() => navigate("/plan"), 1500);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.toUserMessage()
          : "Failed to save career goal. Please try again.";
      throw new Error(message);
    }
  }

  if (loading && data === null) return <LoadingSpinner label="Loading career goal…" />;

  return (
    <div className="career-goal-page">
      <h1 className="career-goal-page__heading">Career Goal</h1>

      {error && data === null && (
        <ErrorBanner message={error} onDismiss={reset} />
      )}

      <CareerGoalForm
        initialValues={data}
        onSubmit={handleSubmit}
        isEditing={data != null}
      />
    </div>
  );
}
