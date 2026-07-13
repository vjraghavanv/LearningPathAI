import { useTheme } from "../context/ThemeContext";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
      title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
      style={{
        background: "none",
        border: "1px solid var(--color-border)",
        borderRadius: "6px",
        padding: "6px 10px",
        color: "var(--color-text-primary)",
        fontSize: "1rem",
        lineHeight: 1,
      }}
    >
      {theme === "light" ? "🌙" : "☀️"}
    </button>
  );
}
