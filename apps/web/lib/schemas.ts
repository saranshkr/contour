import { z } from "zod";

export const prioritySchema = z.enum(["low", "medium", "high"]);
export const issueTypeSchema = z.enum(["Story", "Task"]);
export const assignmentStatusSchema = z.enum([
  "assigned",
  "unassigned_capacity",
  "unassigned_skill_gap",
  "assigned_with_skill_gap",
]);

export const taskInputSchema = z.object({
  text: z.string().trim().min(1, "Task text is required."),
  owner_hint: z.string().trim().min(1).nullable().optional(),
});

export const employeeRecordSchema = z.object({
  id: z.string().trim().min(1),
  name: z.string().trim().min(1),
  role: z.string().trim().min(1),
  skills: z.array(z.string().trim().min(1)).min(1),
  capacity_points: z.number().int().min(0),
  jira_account_id: z.string().trim().min(1),
});

export const sprintRequestSchema = z.object({
  sprint_name: z.string().trim().min(1, "Sprint name is required."),
  goal: z.string().trim().min(1, "Sprint goal is required."),
  tasks: z.array(taskInputSchema).min(1, "Add at least one task."),
});

export const riskFlagSchema = z.object({
  severity: z.enum(["low", "medium", "high"]),
  category: z.string().trim().min(1),
  message: z.string().trim().min(1),
  affected_items: z.array(z.string()).default([]),
  suggested_action: z.string().trim().min(1),
});

export const planItemSchema = z.object({
  task_id: z.string().trim().min(1),
  source_index: z.number().int().min(0),
  task_text: z.string().trim().min(1),
  owner_hint: z.string().trim().min(1).nullable().optional(),
  title: z.string().trim().min(1),
  description: z.string().trim().min(1),
  priority: prioritySchema,
  jira_issue_type: issueTypeSchema,
  story_points: z.number().int().min(1),
  required_skills: z.array(z.string()).default([]),
  estimation_rationale: z.string().trim().min(1),
  recommended_assignee: z.string().trim().min(1).nullable().optional(),
  recommended_assignee_account_id: z.string().trim().min(1).nullable().optional(),
  alternative_assignees: z.array(z.string()).default([]),
  assignment_status: assignmentStatusSchema,
  selection_rationale: z.string().trim().min(1),
  assignment_rationale: z.string().trim().min(1),
  risk_flags: z.array(riskFlagSchema).default([]),
});

export const memberCapacitySummarySchema = z.object({
  member_name: z.string().trim().min(1),
  capacity_points: z.number().int().min(0),
  assigned_points: z.number().int().min(0),
  remaining_points: z.number().int(),
});

export const capacitySummarySchema = z.object({
  total_capacity_points: z.number().int().min(0),
  assigned_points: z.number().int().min(0),
  unassigned_points: z.number().int().min(0),
  remaining_points: z.number().int(),
  allocations: z.array(memberCapacitySummarySchema).default([]),
});

export const sprintPlanSchema = z.object({
  sprint_name: z.string().trim().min(1),
  goal: z.string().trim().min(1),
  plan_items: z.array(planItemSchema).default([]),
  capacity_summary: capacitySummarySchema,
  risks: z.array(riskFlagSchema).default([]),
  approval_state: z.enum(["draft", "approved"]),
});

export const jiraIssueResultSchema = z.object({
  key: z.string().trim().min(1),
  url: z.string().url().nullable().optional(),
  summary: z.string().trim().min(1),
  issue_type: issueTypeSchema,
  assignment_status: assignmentStatusSchema,
  assignee: z.string().trim().min(1).nullable().optional(),
});

export const jiraHandoffResponseSchema = z.object({
  key: z.string().trim().min(1),
  url: z.string().url().nullable().optional(),
  issues: z.array(jiraIssueResultSchema).default([]),
});

export type TaskInput = z.infer<typeof taskInputSchema>;
export type EmployeeRecord = z.infer<typeof employeeRecordSchema>;
export type SprintRequest = z.infer<typeof sprintRequestSchema>;
export type RiskFlag = z.infer<typeof riskFlagSchema>;
export type PlanItem = z.infer<typeof planItemSchema>;
export type SprintPlan = z.infer<typeof sprintPlanSchema>;
export type JiraIssueResult = z.infer<typeof jiraIssueResultSchema>;
export type JiraHandoffResponse = z.infer<typeof jiraHandoffResponseSchema>;

export function createEmptyTask(index = 1): TaskInput {
  return {
    text: "",
    owner_hint: null,
  };
}

export function createEmptySprintRequest(): SprintRequest {
  return {
    sprint_name: "",
    goal: "",
    tasks: [createEmptyTask()],
  };
}
