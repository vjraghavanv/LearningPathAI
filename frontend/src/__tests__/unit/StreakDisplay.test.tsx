import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StreakDisplay } from "../../components/StreakDisplay";

describe("StreakDisplay", () => {
  it("renders streak count and 'days in a row' label when streak > 1", () => {
    render(<StreakDisplay streak={5} />);
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/days in a row/i)).toBeInTheDocument();
  });

  it("renders '1 day in a row' (singular) when streak is 1", () => {
    render(<StreakDisplay streak={1} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/day in a row/i)).toBeInTheDocument();
    // should NOT say "days" (plural)
    const label = screen.getByText(/day in a row/i);
    expect(label.textContent).not.toMatch(/days in a row/i);
  });

  it("renders 0 and motivational prompt when streak is 0", () => {
    render(<StreakDisplay streak={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/start your streak today/i)).toBeInTheDocument();
  });

  it("renders 0 and motivational prompt when streak is null", () => {
    render(<StreakDisplay streak={null} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/start your streak today/i)).toBeInTheDocument();
  });

  it("renders 0 and motivational prompt when streak is undefined", () => {
    render(<StreakDisplay streak={undefined} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/start your streak today/i)).toBeInTheDocument();
  });

  it("has an accessible aria-label with streak count when active", () => {
    render(<StreakDisplay streak={7} />);
    expect(
      screen.getByRole("region", { name: /study streak: 7 days/i })
    ).toBeInTheDocument();
  });

  it("has an accessible aria-label indicating no streak when zero", () => {
    render(<StreakDisplay streak={0} />);
    expect(
      screen.getByRole("region", { name: /no active study streak/i })
    ).toBeInTheDocument();
  });

  it("has an accessible aria-label indicating no streak when null", () => {
    render(<StreakDisplay streak={null} />);
    expect(
      screen.getByRole("region", { name: /no active study streak/i })
    ).toBeInTheDocument();
  });

  it("renders the 🔥 Study Streak heading", () => {
    render(<StreakDisplay streak={3} />);
    expect(screen.getByRole("heading", { name: /study streak/i })).toBeInTheDocument();
  });
});
