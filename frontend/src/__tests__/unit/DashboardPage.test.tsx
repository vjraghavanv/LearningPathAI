import { describe, it, expect } from "vitest";
import { applyOptimisticStatusUpdate, DashboardResponse } from "../../pages/DashboardPage";

// Minimal factory to create a DashboardResponse for testing
function makeDashboard(overrides?: Partial<DashboardResponse>): DashboardResponse {
  return {
    todaysTask: null,
    completionPercentage: 0,
    studyStreak: 3,
    weeklyProgress: null,
    roadmap: null,
    priorityResources: [],
    certificationRecommendations: [],
    recommendedProjects: [],
    ...overrides,
  };
}

describe("applyOptimisticStatusUpdate", () => {
  it("updates the matching resource learningStatus in priorityResources", () => {
    const dashboard = makeDashboard({
      priorityResources: [
        { resourceId: "res-1", title: "Resource 1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
        { resourceId: "res-2", title: "Resource 2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "In Progress");

    expect(updated.priorityResources[0].learningStatus).toBe("In Progress");
    expect(updated.priorityResources[1].learningStatus).toBe("Not Started");
  });

  it("does not mutate the original dashboard object", () => {
    const dashboard = makeDashboard({
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    applyOptimisticStatusUpdate(dashboard, "res-1", "Completed");

    // Original should be unchanged
    expect(dashboard.priorityResources[0].learningStatus).toBe("Not Started");
  });

  it("increments studyStreak by 1 when status becomes Completed", () => {
    const dashboard = makeDashboard({ studyStreak: 5 });
    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Completed");
    expect(updated.studyStreak).toBe(6);
  });

  it("does NOT increment studyStreak when status becomes In Progress", () => {
    const dashboard = makeDashboard({ studyStreak: 5 });
    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "In Progress");
    expect(updated.studyStreak).toBe(5);
  });

  it("does NOT increment studyStreak when status becomes Skipped", () => {
    const dashboard = makeDashboard({ studyStreak: 5 });
    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Skipped");
    expect(updated.studyStreak).toBe(5);
  });

  it("leaves studyStreak unchanged when it is null and status becomes Completed", () => {
    const dashboard = makeDashboard({ studyStreak: null });
    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Completed");
    expect(updated.studyStreak).toBeNull();
  });

  it("recomputes completionPercentage when a not-completed resource is marked Completed", () => {
    const dashboard = makeDashboard({
      completionPercentage: 0,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
        { resourceId: "res-2", title: "R2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Completed");

    // 1 out of 2 non-skipped = 50.0%
    expect(updated.completionPercentage).toBe(50.0);
  });

  it("does NOT double-count if resource is already Completed when marked Completed again", () => {
    const dashboard = makeDashboard({
      completionPercentage: 50,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Completed", aiMetadata: null },
        { resourceId: "res-2", title: "R2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Completed");

    // res-1 was already Completed, so percentage should remain 50%
    expect(updated.completionPercentage).toBe(50);
  });

  it("does NOT change completionPercentage for In Progress status", () => {
    const dashboard = makeDashboard({
      completionPercentage: 25,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "In Progress");

    expect(updated.completionPercentage).toBe(25);
  });

  it("leaves completionPercentage unchanged when it is null and status becomes Completed", () => {
    const dashboard = makeDashboard({
      completionPercentage: null,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Completed");

    expect(updated.completionPercentage).toBeNull();
  });

  it("does not change other dashboard fields when updating a resource", () => {
    const dashboard = makeDashboard({
      roadmap: ["Week 1", "Week 2"],
      certificationRecommendations: ["AWS SAA"],
      recommendedProjects: ["Build a REST API"],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-unknown", "Completed");

    expect(updated.roadmap).toEqual(["Week 1", "Week 2"]);
    expect(updated.certificationRecommendations).toEqual(["AWS SAA"]);
    expect(updated.recommendedProjects).toEqual(["Build a REST API"]);
  });

  it("handles a resourceId that does not exist in priorityResources gracefully", () => {
    const dashboard = makeDashboard({
      studyStreak: 2,
      completionPercentage: 50,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    // Unknown resourceId — streak still increments (optimistic), percentage recomputes with updated list
    const updated = applyOptimisticStatusUpdate(dashboard, "res-unknown", "Completed");

    // Streak increments (optimistic — we don't know the resource isn't in the list)
    expect(updated.studyStreak).toBe(3);
    // priorityResources are unchanged
    expect(updated.priorityResources[0].learningStatus).toBe("Not Started");
  });

  it("correctly computes 100% when all resources are marked Completed", () => {
    const dashboard = makeDashboard({
      completionPercentage: 50,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Completed", aiMetadata: null },
        { resourceId: "res-2", title: "R2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-2", "Completed");

    // 2 out of 2 non-skipped = 100.0%
    expect(updated.completionPercentage).toBe(100.0);
  });

  // --- Skipped status tests (Requirement 5.4: denominator excludes Skipped resources) ---

  it("recomputes completionPercentage when a resource is marked Skipped (removes from denominator)", () => {
    const dashboard = makeDashboard({
      completionPercentage: 50,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Completed", aiMetadata: null },
        { resourceId: "res-2", title: "R2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    // Skipping res-2: 1 completed out of 1 non-skipped = 100%
    const updated = applyOptimisticStatusUpdate(dashboard, "res-2", "Skipped");

    expect(updated.completionPercentage).toBe(100.0);
  });

  it("recomputes completionPercentage to 0% when skipping the only non-completed resource and no completed remain", () => {
    const dashboard = makeDashboard({
      completionPercentage: 0,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    // Skipping res-1: 0 completed out of 0 non-skipped → 0%
    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Skipped");

    expect(updated.completionPercentage).toBe(0);
  });

  it("correctly computes percentage with mixed Completed, Skipped, and Not Started", () => {
    // 3 resources: 1 Completed, 1 Not Started, 1 Not Started (being skipped)
    // After skip: 1 Completed out of 2 non-skipped = 50%
    const dashboard = makeDashboard({
      completionPercentage: 33.3,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Completed", aiMetadata: null },
        { resourceId: "res-2", title: "R2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
        { resourceId: "res-3", title: "R3", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-3", "Skipped");

    // 1 Completed / 2 non-skipped (res-1, res-2) = 50.0%
    expect(updated.completionPercentage).toBe(50.0);
  });

  it("leaves completionPercentage unchanged when null and status becomes Skipped", () => {
    const dashboard = makeDashboard({
      completionPercentage: null,
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Skipped");

    expect(updated.completionPercentage).toBeNull();
  });

  it("marks the Skipped resource as Skipped in priorityResources", () => {
    const dashboard = makeDashboard({
      priorityResources: [
        { resourceId: "res-1", title: "R1", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
        { resourceId: "res-2", title: "R2", url: "", resourceType: "PDF", difficulty: "Beginner", learningStatus: "Not Started", aiMetadata: null },
      ],
    });

    const updated = applyOptimisticStatusUpdate(dashboard, "res-1", "Skipped");

    expect(updated.priorityResources[0].learningStatus).toBe("Skipped");
    expect(updated.priorityResources[1].learningStatus).toBe("Not Started");
  });
});
