import {
  JiraHandoffResponse,
  jiraHandoffResponseSchema,
  SprintPlan,
  sprintPlanSchema,
  SprintRequest,
  sprintRequestSchema,
} from "@/lib/schemas";

export interface PlannerApi {
  loadSampleRequest: () => Promise<SprintRequest>;
  generatePlan: (request: SprintRequest) => Promise<SprintPlan>;
  approvePlan: (plan: SprintPlan) => Promise<SprintPlan>;
  handoffPlan: (projectKey: string, approvedPlan: SprintPlan) => Promise<JiraHandoffResponse>;
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
  approvePlan(plan) {
    const validated = sprintPlanSchema.parse(plan);
    return requestJson({
      path: "/api/v1/plans/approve",
      schema: sprintPlanSchema,
      init: {
        method: "POST",
        body: JSON.stringify(validated),
      },
    });
  },
  handoffPlan(projectKey, approvedPlan) {
    const validatedPlan = sprintPlanSchema.parse(approvedPlan);
    return requestJson({
      path: "/api/v1/jira/handoff",
      schema: jiraHandoffResponseSchema,
      init: {
        method: "POST",
        body: JSON.stringify({
          project_key: projectKey.trim(),
          approved_plan: validatedPlan,
        }),
      },
    });
  },
};
