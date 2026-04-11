import { z } from "zod";

export const backlogItemSchema = z.object({
  id: z.string().trim().min(1, "Backlog item ID is required."),
  title: z.string().trim().min(1, "Backlog item title is required."),
  description: z.string().trim().min(1, "Backlog item description is required."),
  priority: z.string().trim().min(1, "Priority is required."),
  dependencies: z.array(z.string().trim().min(1)).default([]),
  owner_hint: z.string().trim().min(1).nullable().optional(),
  labels: z.array(z.string().trim().min(1)).default([]),
});

export const teamMemberSchema = z.object({
  name: z.string().trim().min(1, "Team member name is required."),
  role: z.string().trim().min(1, "Team member role is required."),
  skills: z.array(z.string().trim().min(1)).min(1, "At least one skill is required."),
  capacity_points: z
    .number({ invalid_type_error: "Capacity must be a number." })
    .int("Capacity must be a whole number.")
    .min(0, "Capacity cannot be negative."),
});

export const sprintRequestSchema = z.object({
  sprint_name: z.string().trim().min(1, "Sprint name is required."),
  goal: z.string().trim().min(1, "Sprint goal is required."),
  backlog_items: z.array(backlogItemSchema).min(1, "Add at least one backlog item."),
  team_members: z.array(teamMemberSchema).min(1, "Add at least one team member."),
});

export const enrichedBacklogItemSchema = backlogItemSchema.extend({
  estimated_points: z.number().int().min(1),
  required_skills: z.array(z.string()).default([]),
  ambiguity_flags: z.array(z.string()).default([]),
  dependency_signals: z.array(z.string()).default([]),
  analysis_confidence: z.number().min(0).max(1),
});

export const sprintPlanItemSchema = enrichedBacklogItemSchema.extend({
  recommended_assignee: z.string().trim().min(1),
  alternative_assignees: z.array(z.string()).default([]),
  selection_rationale: z.string().trim().min(1),
  assignment_rationale: z.string().trim().min(1),
});

export const memberCapacitySummarySchema = z.object({
  member_name: z.string().trim().min(1),
  capacity_points: z.number().int().min(0),
  assigned_points: z.number().int().min(0),
  remaining_points: z.number().int(),
});

export const capacitySummarySchema = z.object({
  total_capacity_points: z.number().int().min(0),
  selected_points: z.number().int().min(0),
  remaining_points: z.number().int(),
  allocations: z.array(memberCapacitySummarySchema).default([]),
});

export const riskFlagSchema = z.object({
  severity: z.enum(["low", "medium", "high"]),
  category: z.string().trim().min(1),
  message: z.string().trim().min(1),
  affected_items: z.array(z.string()).default([]),
  suggested_action: z.string().trim().min(1),
});

export const sprintPlanSchema = z.object({
  sprint_name: z.string().trim().min(1),
  goal: z.string().trim().min(1),
  selected_items: z.array(sprintPlanItemSchema).default([]),
  deferred_items: z.array(enrichedBacklogItemSchema).default([]),
  capacity_summary: capacitySummarySchema,
  risks: z.array(riskFlagSchema).default([]),
  approval_state: z.enum(["draft", "approved"]),
});

export const jiraHandoffResponseSchema = z.object({
  key: z.string().trim().min(1),
  url: z.string().url().nullable().optional(),
});

export type BacklogItem = z.infer<typeof backlogItemSchema>;
export type TeamMember = z.infer<typeof teamMemberSchema>;
export type SprintRequest = z.infer<typeof sprintRequestSchema>;
export type EnrichedBacklogItem = z.infer<typeof enrichedBacklogItemSchema>;
export type SprintPlanItem = z.infer<typeof sprintPlanItemSchema>;
export type SprintPlan = z.infer<typeof sprintPlanSchema>;
export type JiraHandoffResponse = z.infer<typeof jiraHandoffResponseSchema>;

export function createEmptyBacklogItem(index = 1): BacklogItem {
  return {
    id: `CTR-${100 + index}`,
    title: "",
    description: "",
    priority: "Medium",
    dependencies: [],
    owner_hint: null,
    labels: [],
  };
}

export function createEmptyTeamMember(index = 1): TeamMember {
  return {
    name: "",
    role: "",
    skills: [],
    capacity_points: 0,
  };
}

export function createEmptySprintRequest(): SprintRequest {
  return {
    sprint_name: "",
    goal: "",
    backlog_items: [createEmptyBacklogItem()],
    team_members: [createEmptyTeamMember()],
  };
}
