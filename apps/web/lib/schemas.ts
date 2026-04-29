import { z } from "zod";

export const prioritySchema = z.enum(["low", "medium", "high"]);
export const issueTypeSchema = z.enum(["Story", "Task"]);
export const workItemStatusSchema = z.enum(["todo", "in_progress", "blocked", "done"]);
export const assignmentStatusSchema = z.enum([
  "assigned",
  "unassigned_capacity",
  "unassigned_skill_gap",
  "assigned_with_skill_gap",
]);

export const backlogItemSchema = z
  .object({
    id: z.string().trim().min(1).nullable().optional(),
    text: z.string().trim().min(1).nullable().optional(),
    title: z.string().trim().min(1).nullable().optional(),
    description: z.string().trim().min(1).nullable().optional(),
    acceptance_criteria: z.array(z.string().trim().min(1)).default([]),
    task_type: issueTypeSchema.nullable().optional(),
    priority: prioritySchema.nullable().optional(),
    status: workItemStatusSchema.nullable().optional(),
    owner_hint: z.string().trim().min(1).nullable().optional(),
  })
  .refine((value) => Boolean(value.text || (value.title && value.description)), {
    message: "Backlog item needs text or both title and description.",
    path: ["text"],
  });

export const engineerProfileSchema = z.object({
  id: z.string().trim().min(1),
  name: z.string().trim().min(1),
  role: z.string().trim().min(1),
  skills: z.array(z.string().trim().min(1)).min(1),
  capacity_points: z.number().int().min(0),
  jira_account_id: z.string().trim().min(1),
});

export const teamCapacitySchema = z.object({
  available_points: z.number().int().min(0).nullable().optional(),
  buffer_points: z.number().int().min(0).default(0),
});

export const sprintPlanInputSchema = z.object({
  sprint_name: z.string().trim().min(1, "Sprint name is required."),
  goal: z.string().trim().min(1, "Sprint goal is required."),
  tasks: z.array(backlogItemSchema).min(1, "Add at least one task."),
  engineer_profiles: z.array(engineerProfileSchema).default([]),
  team_capacity: teamCapacitySchema.nullable().optional(),
  expected_constraints: z
    .object({
      should_fit_capacity: z.boolean().nullable().optional(),
      allow_missing_acceptance_criteria: z.boolean().default(false),
      allow_skill_gaps: z.boolean().default(false),
      allow_malformed_input: z.boolean().default(false),
    })
    .nullable()
    .optional(),
});

export const riskFlagSchema = z.object({
  severity: z.enum(["low", "medium", "high"]),
  category: z.string().trim().min(1),
  message: z.string().trim().min(1),
  affected_items: z.array(z.string()).default([]),
  suggested_action: z.string().trim().min(1),
});

export const validationMessageSchema = z.object({
  code: z.string().trim().min(1),
  message: z.string().trim().min(1),
  field: z.string().trim().min(1).nullable().optional(),
  task_id: z.string().trim().min(1).nullable().optional(),
});

export const validationMetricsSchema = z.object({
  total_points: z.number().int().min(0),
  available_capacity: z.number().int().min(0),
  capacity_utilization: z.number().min(0),
  overloaded_engineers: z.array(z.string()).default([]),
  assigned_item_count: z.number().int().min(0),
  unassigned_item_count: z.number().int().min(0),
});

export const sprintPlanValidationResultSchema = z.object({
  is_valid: z.boolean(),
  errors: z.array(validationMessageSchema).default([]),
  warnings: z.array(validationMessageSchema).default([]),
  metrics: validationMetricsSchema,
});

export const planItemSchema = z.object({
  task_id: z.string().trim().min(1),
  source_index: z.number().int().min(0),
  task_text: z.string().trim().min(1),
  owner_hint: z.string().trim().min(1).nullable().optional(),
  backlog_item_id: z.string().trim().min(1).nullable().optional(),
  title: z.string().trim().min(1),
  description: z.string().trim().min(1),
  acceptance_criteria: z.array(z.string().trim().min(1)).default([]),
  priority: prioritySchema,
  jira_issue_type: issueTypeSchema,
  status: workItemStatusSchema.default("todo"),
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
  validation_result: sprintPlanValidationResultSchema.nullable().optional(),
  approval_state: z.enum(["draft", "approved"]),
  engineer_profiles: z.array(engineerProfileSchema).default([]),
  team_capacity: teamCapacitySchema.nullable().optional(),
});

export const jiraIssuePreviewSchema = z.object({
  issue_type: z.string().trim().min(1),
  fields: z.record(z.string(), z.unknown()),
  task_id: z.string().trim().min(1).nullable().optional(),
});

export const jiraIssueResultSchema = z.object({
  key: z.string().trim().min(1),
  url: z.string().url().nullable().optional(),
  summary: z.string().trim().min(1),
  issue_type: issueTypeSchema,
  assignment_status: assignmentStatusSchema,
  assignee: z.string().trim().min(1).nullable().optional(),
  task_id: z.string().trim().min(1).nullable().optional(),
});

export const jiraSyncStatusSchema = z.enum([
  "NOT_STARTED",
  "DRY_RUN_PASSED",
  "SYNC_IN_PROGRESS",
  "SYNC_SUCCEEDED",
  "SYNC_FAILED",
  "PARTIAL_FAILURE",
]);

export const jiraSyncStateSchema = z.object({
  idempotency_key: z.string().trim().min(1),
  project_key: z.string().trim().min(1),
  status: jiraSyncStatusSchema,
  epic_key: z.string().trim().min(1).nullable().optional(),
  child_issue_keys: z.record(z.string(), z.string()).default({}),
  validation_errors: z.array(validationMessageSchema).default([]),
  validation_warnings: z.array(validationMessageSchema).default([]),
  last_error: z.string().trim().min(1).nullable().optional(),
});

export const jiraDryRunRequestSchema = z.object({
  project_key: z.string().trim().min(1),
  approved_plan: sprintPlanSchema,
  accept_warnings: z.boolean().default(false),
  engineer_profiles: z.array(engineerProfileSchema).default([]),
  team_capacity: teamCapacitySchema.nullable().optional(),
});

export const jiraDryRunResponseSchema = z.object({
  idempotency_key: z.string().trim().min(1),
  epic_payload_preview: jiraIssuePreviewSchema,
  child_issue_payload_previews: z.array(jiraIssuePreviewSchema).default([]),
  validation_errors: z.array(validationMessageSchema).default([]),
  validation_warnings: z.array(validationMessageSchema).default([]),
  estimated_jira_objects: z.number().int().min(0),
  safe_to_execute: z.boolean(),
  sync_state: jiraSyncStateSchema,
});

export const jiraHandoffResponseSchema = z.object({
  key: z.string().trim().min(1),
  url: z.string().url().nullable().optional(),
  issues: z.array(jiraIssueResultSchema).default([]),
  sync_state: jiraSyncStateSchema.nullable().optional(),
});

export type BacklogItem = z.infer<typeof backlogItemSchema>;
export type EngineerProfile = z.infer<typeof engineerProfileSchema>;
export type TeamCapacity = z.infer<typeof teamCapacitySchema>;
export type SprintPlanInput = z.infer<typeof sprintPlanInputSchema>;
export type RiskFlag = z.infer<typeof riskFlagSchema>;
export type ValidationMessage = z.infer<typeof validationMessageSchema>;
export type SprintPlanValidationResult = z.infer<typeof sprintPlanValidationResultSchema>;
export type PlanItem = z.infer<typeof planItemSchema>;
export type SprintPlan = z.infer<typeof sprintPlanSchema>;
export type JiraIssuePreview = z.infer<typeof jiraIssuePreviewSchema>;
export type JiraIssueResult = z.infer<typeof jiraIssueResultSchema>;
export type JiraSyncState = z.infer<typeof jiraSyncStateSchema>;
export type JiraDryRunRequest = z.infer<typeof jiraDryRunRequestSchema>;
export type JiraDryRunResponse = z.infer<typeof jiraDryRunResponseSchema>;
export type JiraHandoffResponse = z.infer<typeof jiraHandoffResponseSchema>;

export type TaskInput = BacklogItem;
export type EmployeeRecord = EngineerProfile;
export type SprintRequest = SprintPlanInput;

export const taskInputSchema = backlogItemSchema;
export const employeeRecordSchema = engineerProfileSchema;
export const sprintRequestSchema = sprintPlanInputSchema;

export function createEmptyTask(): TaskInput {
  return {
    id: null,
    text: "",
    title: null,
    description: null,
    acceptance_criteria: [],
    task_type: null,
    priority: null,
    status: null,
    owner_hint: null,
  };
}

export function createEmptySprintRequest(): SprintRequest {
  return {
    sprint_name: "",
    goal: "",
    tasks: [createEmptyTask()],
    engineer_profiles: [],
    team_capacity: null,
    expected_constraints: null,
  };
}
