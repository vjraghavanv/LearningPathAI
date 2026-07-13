import { Link } from "react-router-dom";
import "./OnboardingPrompt.css";

interface OnboardingPromptProps {
  /** Optional override for the CTA link destination */
  careerGoalPath?: string;
}

/**
 * Displayed on the Dashboard when no active Learning_Plan exists.
 * Directs the user to set up their Career Goal so a plan can be generated.
 */
export function OnboardingPrompt({
  careerGoalPath = "/career",
}: OnboardingPromptProps) {
  return (
    <div className="onboarding" role="region" aria-label="Get started">
      <div className="onboarding__icon" aria-hidden="true">🎯</div>
      <h2 className="onboarding__title">Set up your Career Goal to get started</h2>
      <p className="onboarding__body">
        You don't have an active learning plan yet. Tell us your career goal,
        skill level, and weekly study availability — and we'll generate a
        personalized roadmap for you.
      </p>
      <Link to={careerGoalPath} className="onboarding__cta">
        Set up Career Goal
      </Link>
    </div>
  );
}
