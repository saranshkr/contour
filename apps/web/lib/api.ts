import {
  EmployeeRecord,
  JiraDryRunResponse,
  jiraDryRunResponseSchema,
  JiraHandoffResponse,
  employeeRecordSchema,
  jiraHandoffResponseSchema,
  SprintPlan,
  sprintPlanSchema,
  SprintRequest,
  sprintRequestSchema,
  TeamCapacity,
  EngineerProfile,
} from "@/lib/schemas";

type PlanningContext = {
  engineer_profiles?: EngineerProfile[];
  team_capacity?: TeamCapacity | null;
};

type JiraActionOptions = {
  acceptWarnings?: boolean;
  context?: PlanningContext;
};

export interface PlannerApi {
  loadEmployees: () => Promise<EmployeeRecord[]>;
  loadSampleRequest: () => Promise<SprintRequest>;
  generatePlan: (request: SprintRequest) => Promise<SprintPlan>;
  approvePlan: (plan: SprintPlan, context?: PlanningContext) => Promise<SprintPlan>;
  dryRunPlan: (projectKey: string, approvedPlan: SprintPlan, options?: JiraActionOptions) => Promise<JiraDryRunResponse>;
  handoffPlan: (projectKey: string, approvedPlan: SprintPlan, options?: JiraActionOptions) => Promise<JiraHandoffResponse>;
}

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function getApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");
}

async function requestJson<T>({
  path,
  schema,
  init,
}: {
  path: string;
  schema: { parse: (value: unknown) => T };
  init?: RequestInit;
}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "Request failed.";
    throw new Error(detail);
  }

  const payload = await response.json();
  return schema.parse(payload);
}

export const plannerApi: PlannerApi = {
  loadEmployees() {
    return requestJson({
      path: "/api/v1/employees",
      schema: employeeRecordSchema.array(),
      init: { method: "GET" },
    });
  },
  loadSampleRequest() {
    return requestJson({
      path: "/api/v1/sample-request",
      schema: sprintRequestSchema,
      init: { method: "GET" },
    });
  },
  generatePlan(request) {
    const validated = sprintRequestSchema.parse(request);
    return requestJson({
      path: "/api/v1/plans/generate",
      schema: sprintPlanSchema,
      init: {
        method: "POST",
        body: JSON.stringify(validated),
      },
    });
  },
  approvePlan(plan, context) {
    const validated = sprintPlanSchema.parse(plan);
    return requestJson({
      path: "/api/v1/plans/approve",
      schema: sprintPlanSchema,
      init: {
        method: "POST",
        body: JSON.stringify({
          approved_plan: validated,
          ...buildContextPayload(validated, context),
        }),
      },
    });
  },
  dryRunPlan(projectKey, approvedPlan, options) {
    const validatedPlan = sprintPlanSchema.parse(approvedPlan);
    return requestJson({
      path: "/api/v1/jira/dry-run",
      schema: jiraDryRunResponseSchema,
      init: {
        method: "POST",
        body: JSON.stringify({
          project_key: projectKey.trim(),
          approved_plan: validatedPlan,
          accept_warnings: options?.acceptWarnings ?? false,
          ...buildContextPayload(validatedPlan, options?.context),
        }),
      },
    });
  },
  handoffPlan(projectKey, approvedPlan, options) {
    const validatedPlan = sprintPlanSchema.parse(approvedPlan);
    return requestJson({
      path: "/api/v1/jira/handoff",
      schema: jiraHandoffResponseSchema,
      init: {
        method: "POST",
        body: JSON.stringify({
          project_key: projectKey.trim(),
          approved_plan: validatedPlan,
          accept_warnings: options?.acceptWarnings ?? false,
          ...buildContextPayload(validatedPlan, options?.context),
        }),
      },
    });
  },
};

function buildContextPayload(plan: SprintPlan, context?: PlanningContext) {
  return {
    engineer_profiles: context?.engineer_profiles?.length
      ? context.engineer_profiles
      : plan.engineer_profiles,
    team_capacity:
      context && "team_capacity" in context
        ? context.team_capacity
        : plan.team_capacity ?? null,
  };
}
