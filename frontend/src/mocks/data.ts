/**
 * Shared fixture data for the local development mock API.
 * Mirrors the shapes used in e2e/helpers/mock-api.ts.
 */

const TODAY = new Date().toISOString().split("T")[0];

export let resources = [
  {
    userId: "local-user-1",
    resourceId: "RESOURCE#001",
    title: "AWS IAM Deep Dive",
    url: "https://docs.aws.amazon.com/iam",
    resourceType: "Documentation",
    difficulty: "Beginner",
    learningStatus: "Completed",
    tags: ["aws", "iam", "security"],
    technology: "AWS",
    estimatedDuration: "2 hours",
    aiMetadata: {
      priorityScore: 85,
      summary: "Comprehensive guide to AWS Identity and Access Management. Covers users, roles, policies, and best practices.",
      skills: ["IAM", "Security", "AWS"],
      difficulty: "Beginner",
      estimatedTime: "2 hours",
      whyLearnNow: "IAM is foundational for any AWS certification and cloud role.",
      recommendedWeek: 1,
    },
    createdAt: "2026-07-01T09:00:00Z",
    updatedAt: "2026-07-10T14:00:00Z",
  },
  {
    userId: "local-user-1",
    resourceId: "RESOURCE#002",
    title: "Docker & Kubernetes: The Practical Guide",
    url: "https://www.udemy.com/course/docker-kubernetes-the-practical-guide/",
    resourceType: "Online Course",
    difficulty: "Intermediate",
    learningStatus: "In Progress",
    tags: ["docker", "kubernetes", "devops"],
    technology: "Docker",
    estimatedDuration: "8 hours",
    aiMetadata: {
      priorityScore: 92,
      summary: "Hands-on course covering Docker containers and Kubernetes orchestration from scratch to production.",
      skills: ["Docker", "Kubernetes", "DevOps"],
      difficulty: "Intermediate",
      estimatedTime: "8 hours",
      whyLearnNow: "Container orchestration is a core DevOps skill in 2026.",
      recommendedWeek: 2,
    },
    createdAt: "2026-07-05T10:00:00Z",
    updatedAt: "2026-07-12T11:00:00Z",
  },
  {
    userId: "local-user-1",
    resourceId: "RESOURCE#003",
    title: "AWS EC2 Auto Scaling Deep Dive",
    url: "https://docs.aws.amazon.com/autoscaling/ec2/userguide/",
    resourceType: "Technical Article",
    difficulty: "Intermediate",
    learningStatus: "Not Started",
    tags: ["aws", "ec2", "autoscaling"],
    technology: "AWS",
    estimatedDuration: "1.5 hours",
    aiMetadata: {
      priorityScore: 78,
      summary: "Official AWS documentation on EC2 Auto Scaling groups, launch templates, and scaling policies.",
      skills: ["EC2", "Auto Scaling", "AWS"],
      difficulty: "Intermediate",
      estimatedTime: "1.5 hours",
      whyLearnNow: "Auto Scaling is heavily tested in the AWS SAA-C03 exam.",
      recommendedWeek: 3,
    },
    createdAt: "2026-07-08T08:00:00Z",
    updatedAt: "2026-07-08T08:00:00Z",
  },
  {
    userId: "local-user-1",
    resourceId: "RESOURCE#004",
    title: "Terraform: Infrastructure as Code",
    url: "https://developer.hashicorp.com/terraform/tutorials",
    resourceType: "Documentation",
    difficulty: "Intermediate",
    learningStatus: "Not Started",
    tags: ["terraform", "iac", "devops"],
    technology: "Terraform",
    estimatedDuration: "4 hours",
    aiMetadata: {
      priorityScore: 70,
      summary: "Official HashiCorp tutorials for learning Terraform from basics to advanced state management.",
      skills: ["Terraform", "IaC", "DevOps"],
      difficulty: "Intermediate",
      estimatedTime: "4 hours",
      whyLearnNow: "Terraform is the industry standard for cloud infrastructure provisioning.",
      recommendedWeek: 4,
    },
    createdAt: "2026-07-09T07:00:00Z",
    updatedAt: "2026-07-09T07:00:00Z",
  },
  {
    userId: "local-user-1",
    resourceId: "RESOURCE#005",
    title: "Python for DevOps Engineers",
    url: "https://www.youtube.com/watch?v=python-devops",
    resourceType: "YouTube Video",
    difficulty: "Beginner",
    learningStatus: "Skipped",
    tags: ["python", "automation", "devops"],
    technology: "Python",
    estimatedDuration: "3 hours",
    aiMetadata: {
      priorityScore: 55,
      summary: "Practical Python scripting for automation, AWS Boto3 usage, and CI/CD pipeline scripting.",
      skills: ["Python", "Automation", "Boto3"],
      difficulty: "Beginner",
      estimatedTime: "3 hours",
      whyLearnNow: "Python scripting accelerates DevOps automation tasks.",
      recommendedWeek: 5,
    },
    createdAt: "2026-07-10T06:00:00Z",
    updatedAt: "2026-07-11T09:00:00Z",
  },
];

export const careerGoal = {
  userId: "local-user-1",
  careerGoal: "Become AWS Cloud Engineer",
  currentSkillLevel: "Intermediate",
  weeklyStudyHours: 14,
  preferredLearningPace: "Moderate",
  targetCompletionDate: "2026-12-31",
  createdAt: "2026-07-01T08:00:00Z",
  updatedAt: "2026-07-13T10:00:00Z",
};

export const learningPlan = {
  userId: "local-user-1",
  resourceId: "PLAN#active",
  dailySchedule: [
    { day: 1, date: TODAY, resourceId: "RESOURCE#002", estimatedDuration: "2 hours", recommendationReason: "Docker containerisation is your next priority — it builds on your completed IAM knowledge for cloud deployments." },
    { day: 2, date: TODAY, resourceId: "RESOURCE#002", estimatedDuration: "2 hours", recommendationReason: "Continuing the Docker & Kubernetes course keeps momentum on container fundamentals." },
    { day: 3, date: TODAY, resourceId: "RESOURCE#003", estimatedDuration: "1.5 hours", recommendationReason: "EC2 Auto Scaling is directly tested in AWS SAA-C03 — tackle it mid-week while energy is high." },
    { day: 4, date: TODAY, resourceId: "RESOURCE#002", estimatedDuration: "2 hours", recommendationReason: "Third Docker session focuses on Kubernetes — critical for the DevOps role you are targeting." },
    { day: 5, date: TODAY, resourceId: "RESOURCE#004", estimatedDuration: "2 hours", recommendationReason: "Terraform pairs naturally with what you have learned this week — start with basics and state management." },
    { day: 6, date: TODAY, resourceId: "RESOURCE#003", estimatedDuration: "1 hour", recommendationReason: "Review EC2 Auto Scaling concepts to reinforce what you read earlier this week." },
    { day: 7, date: TODAY, resourceId: "RESOURCE#004", estimatedDuration: "1.5 hours", recommendationReason: "End the week with Terraform practice — applying IaC concepts consolidates your cloud skills." },
  ],
  weeklyRoadmap: [
    "Week 1: Docker & Kubernetes + EC2 Auto Scaling",
    "Week 2: Terraform IaC + AWS VPC Networking",
    "Week 3: CI/CD with GitHub Actions + AWS CodePipeline",
    "Week 4: AWS SAA-C03 Exam Practice Tests",
  ],
  recommendedProjects: [
    "Deploy a containerised Node.js API to ECS Fargate with auto-scaling",
    "Provision a multi-tier AWS VPC with Terraform",
    "Build a CI/CD pipeline with GitHub Actions deploying to Lambda",
  ],
  certificationRecommendations: [
    "AWS Solutions Architect Associate (SAA-C03) — target in 8 weeks",
    "Certified Kubernetes Administrator (CKA) — target in 16 weeks",
  ],
  estimatedCompletionTimeline: "6 months (by December 2026)",
  generatedAt: new Date().toISOString(),
};

export const streak = {
  userId: "local-user-1",
  resourceId: "STREAK#current",
  currentStreak: 4,
  lastCompletionDate: TODAY,
};

export function buildDashboard() {
  const nonSkipped = resources.filter((r) => r.learningStatus !== "Skipped");
  const completed = nonSkipped.filter((r) => r.learningStatus === "Completed");
  const completionPercentage =
    nonSkipped.length > 0
      ? Math.round((completed.length / nonSkipped.length) * 1000) / 10
      : 0;

  const todaysEntry = learningPlan.dailySchedule[0];
  const todaysResource = resources.find((r) => r.resourceId === todaysEntry?.resourceId);

  const priorityResources = resources
    .filter((r) => r.learningStatus !== "Skipped" && r.learningStatus !== "Completed")
    .sort((a, b) => (b.aiMetadata?.priorityScore ?? 0) - (a.aiMetadata?.priorityScore ?? 0))
    .slice(0, 5)
    .map((r) => ({
      resourceId: r.resourceId,
      title: r.title,
      url: r.url,
      resourceType: r.resourceType,
      difficulty: r.difficulty,
      learningStatus: r.learningStatus,
      priorityScore: r.aiMetadata?.priorityScore ?? 0,
      recommendationReason: r.aiMetadata?.whyLearnNow ?? "",
    }));

  return {
    userId: "local-user-1",
    todaysTask: todaysResource
      ? {
          resourceId: todaysResource.resourceId,
          title: todaysResource.title,
          url: todaysResource.url,
          resourceType: todaysResource.resourceType,
          estimatedDuration: todaysEntry.estimatedDuration,
          recommendationReason: todaysEntry.recommendationReason,
          learningStatus: todaysResource.learningStatus,
          priorityScore: todaysResource.aiMetadata?.priorityScore ?? 0,
        }
      : null,
    completionPercentage,
    studyStreak: streak.currentStreak,
    weeklyProgress: [
      { day: "Mon", completedMinutes: 120, targetMinutes: 120 },
      { day: "Tue", completedMinutes: 90, targetMinutes: 120 },
      { day: "Wed", completedMinutes: 120, targetMinutes: 120 },
      { day: "Thu", completedMinutes: 0, targetMinutes: 120 },
      { day: "Fri", completedMinutes: 0, targetMinutes: 120 },
      { day: "Sat", completedMinutes: 60, targetMinutes: 120 },
      { day: "Sun", completedMinutes: 0, targetMinutes: 120 },
    ],
    roadmap: learningPlan.weeklyRoadmap,
    priorityResources,
    certificationRecommendations: learningPlan.certificationRecommendations,
    recommendedProjects: learningPlan.recommendedProjects,
    message: null,
  };
}
