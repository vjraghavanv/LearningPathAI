/**
 * Shared Resource type definitions used by the Resource Management and Search views.
 */

export type ResourceType =
  | "Technical Article"
  | "Documentation"
  | "YouTube Video"
  | "Online Course"
  | "PDF"
  | "GitHub Repository";

export type Difficulty = "Beginner" | "Intermediate" | "Advanced";

export type LearningStatus =
  | "Not Started"
  | "In Progress"
  | "Completed"
  | "Skipped";

export interface Resource {
  resourceId: string;
  userId?: string;
  title: string;
  url: string;
  resourceType: ResourceType;
  estimatedDuration?: string;
  difficulty?: Difficulty;
  tags?: string[];
  technology?: string;
  learningStatus: LearningStatus;
  completionTimestamp?: string | null;
  completionPercentage?: number;
  aiMetadata?: {
    priorityScore: number;
    summary?: string;
    skills?: string[];
    difficulty?: string;
    estimatedTime?: string;
    whyLearnNow?: string;
    recommendedWeek?: number;
  } | null;
  createdAt?: string;
  updatedAt?: string;
}

/** Fields submitted when creating or editing a resource */
export interface ResourceFormData {
  title: string;
  url: string;
  resourceType: ResourceType | "";
  estimatedDuration: string;
  difficulty: Difficulty | "";
  tags: string;       // comma-separated
  technology: string;
  learningStatus: LearningStatus;
}

export const RESOURCE_TYPES: ResourceType[] = [
  "Technical Article",
  "Documentation",
  "YouTube Video",
  "Online Course",
  "PDF",
  "GitHub Repository",
];

export const DIFFICULTIES: Difficulty[] = ["Beginner", "Intermediate", "Advanced"];

export const LEARNING_STATUSES: LearningStatus[] = [
  "Not Started",
  "In Progress",
  "Completed",
  "Skipped",
];
