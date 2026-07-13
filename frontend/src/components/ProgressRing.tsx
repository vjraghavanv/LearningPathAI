import "./ProgressRing.css";

interface ProgressRingProps {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

/**
 * SVG circular progress ring showing a completion percentage (0–100).
 */
export function ProgressRing({
  percentage,
  size = 120,
  strokeWidth = 10,
  label,
}: ProgressRingProps) {
  const clampedPct = Math.min(100, Math.max(0, percentage));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clampedPct / 100) * circumference;
  const center = size / 2;

  const ariaLabel = label
    ? `${label}: ${clampedPct}%`
    : `Completion: ${clampedPct}%`;

  return (
    <div className="progress-ring" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        role="img"
        aria-label={ariaLabel}
        className="progress-ring__svg"
      >
        {/* Track */}
        <circle
          className="progress-ring__track"
          cx={center}
          cy={center}
          r={radius}
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Filled arc */}
        <circle
          className="progress-ring__arc"
          cx={center}
          cy={center}
          r={radius}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${center} ${center})`}
        />
      </svg>
      <div className="progress-ring__label" aria-hidden="true">
        <span className="progress-ring__pct">{clampedPct}%</span>
        {label && <span className="progress-ring__text">{label}</span>}
      </div>
    </div>
  );
}
