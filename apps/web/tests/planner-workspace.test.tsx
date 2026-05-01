import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PlannerWorkspace } from "@/components/planner-workspace";
import { PlannerApi } from "@/lib/api";
import {
  EmployeeRecord,
  JiraDryRunResponse,
  JiraHandoffResponse,
  SprintPlan,
  SprintRequest,
} from "@/lib/schemas";

const employees: EmployeeRecord[] = [
  {
    id: "emp-avery",
    name: "Avery",
    role: "Frontend Engineer",
    skills: ["frontend", "react", "ui"],
    capacity_points: 8,
    jira_account_id: "acct-avery",
  },
];

const sampleRequest: SprintRequest = {
  sprint_name: "Sprint 18",
  goal: "Ship the Contour MVP flow",
  tasks: [
    {
      id: "BL-1",
      text: "Build the planning workspace for the web app.",
      owner_hint: "Avery",
      acceptance_criteria: ["Workspace loads sample sprint data."],
    },
  ],
  engineer_profiles: [],
  team_capacity: null,
  expected_constraints: null,
};

const draftPlan: SprintPlan = {
  sprint_name: "Sprint 18",
  goal: "Ship the Contour MVP flow",
  plan_items: [
    {
      task_id: "TASK-1",
      source_index: 0,
      task_text: "Build the planning workspace for the web app.",
      owner_hint: "Avery",
      backlog_item_id: "BL-1",
      title: "Build planning workspace",
      description: "Create the intake and review UI for Contour.",
      acceptance_criteria: ["Workspace loads sample sprint data."],
      priority: "high",
      jira_issue_type: "Story",
      status: "todo",
      story_points: 5,
      required_skills: ["frontend", "ui"],
      estimation_rationale: "High-priority UI work.",
      recommended_assignee: "Avery",
      recommended_assignee_account_id: "acct-avery",
      alternative_assignees: [],
      assignment_status: "assigned",
      selection_rationale: "Included in the sprint scope.",
      assignment_rationale: "Avery has the strongest frontend context.",
      risk_flags: [],
    },
  ],
  capacity_summary: {
    total_capacity_points: 8,
    assigned_points: 5,
    unassigned_points: 0,
    remaining_points: 3,
    allocations: [
      {
        member_name: "Avery",
        capacity_points: 8,
        assigned_points: 5,
        remaining_points: 3,
      },
    ],
  },
  risks: [],
  validation_result: {
    is_valid: false,
    errors: [
      {
        code: "missing_task_description",
        message: "TASK-1 is missing a task description.",
        field: "description",
        task_id: "TASK-1",
      },
    ],
    warnings: [
      {
        code: "missing_acceptance_criteria",
        message: "TASK-1 has no acceptance criteria.",
        field: "acceptance_criteria",
        task_id: "TASK-1",
      },
    ],
    metrics: {
      total_points: 5,
      available_capacity: 8,
      capacity_utilization: 0.625,
      overloaded_engineers: [],
      assigned_item_count: 1,
      unassigned_item_count: 0,
    },
  },
  approval_state: "draft",
  engineer_profiles: employees,
  team_capacity: null,
};

const dryRunResponse: JiraDryRunResponse = {
  idempotency_key: "CTR-abc123",
  epic_payload_preview: {
    issue_type: "Epic",
    fields: { summary: "Sprint 18: Ship the Contour MVP flow" },
    task_id: null,
  },
  child_issue_payload_previews: [
    {
      issue_type: "Story",
      fields: { summary: "Build planning workspace" },
      task_id: "TASK-1",
    },
  ],
  validation_errors: [],
  validation_warnings: draftPlan.validation_result?.warnings ?? [],
  estimated_jira_objects: 2,
  safe_to_execute: true,
  sync_state: {
    idempotency_key: "CTR-abc123",
    project_key: "CTR",
    status: "DRY_RUN_PASSED",
    epic_key: null,
    child_issue_keys: {},
    validation_errors: [],
    validation_warnings: draftPlan.validation_result?.warnings ?? [],
    last_error: null,
  },
};

const approvedPlan: SprintPlan = {
  ...draftPlan,
  validation_result: {
    ...draftPlan.validation_result!,
    is_valid: true,
    errors: [],
    warnings: draftPlan.validation_result!.warnings,
  },
  approval_state: "approved",
};

const jiraResponse: JiraHandoffResponse = {
  key: "CTR-900",
  url: "https://example.atlassian.net/browse/CTR-900",
  issues: [
    {
      key: "CTR-901",
      url: "https://example.atlassian.net/browse/CTR-901",
      summary: "Build planning workspace",
      issue_type: "Story",
      assignment_status: "assigned",
      assignee: "Avery",
      task_id: "TASK-1",
    },
  ],
  sync_state: {
    idempotency_key: "CTR-abc123",
    project_key: "CTR",
    status: "SYNC_SUCCEEDED",
    epic_key: "CTR-900",
    child_issue_keys: { "TASK-1": "CTR-901" },
    validation_errors: [],
    validation_warnings: [],
    last_error: null,
  },
};

function buildApi(overrides: Partial<PlannerApi> = {}): PlannerApi {
  return {
    loadEmployees: vi.fn().mockResolvedValue(employees),
    loadSampleRequest: vi.fn().mockResolvedValue(sampleRequest),
    generatePlan: vi.fn().mockResolvedValue(draftPlan),
    approvePlan: vi.fn().mockResolvedValue(approvedPlan),
    dryRunPlan: vi.fn().mockResolvedValue(dryRunResponse),
    handoffPlan: vi.fn().mockResolvedValue(jiraResponse),
    ...overrides,
  };
}

describe("PlannerWorkspace", () => {
  it("renders validation errors correctly", async () => {
    const api = buildApi();
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    expect(await screen.findByText(/TASK-1 is missing a task description/i)).toBeInTheDocument();
  });

  it("renders warnings correctly", async () => {
    const api = buildApi();
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    expect(await screen.findByText(/validation warnings/i)).toBeInTheDocument();
    expect(screen.getByText(/TASK-1 has no acceptance criteria/i)).toBeInTheDocument();
  });

  it("renders Jira dry-run preview correctly", async () => {
    const api = buildApi({
      generatePlan: vi.fn().mockResolvedValue({ ...draftPlan, validation_result: { ...draftPlan.validation_result!, is_valid: true, errors: [] } }),
    });
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));
    await user.click(screen.getByRole("checkbox", { name: /accept validation warnings/i }));
    await user.click(screen.getByRole("button", { name: /run jira dry-run/i }));

    expect(await screen.findByText(/Jira dry-run preview/i)).toBeInTheDocument();
    expect(screen.getByText(/CTR-abc123/i)).toBeInTheDocument();
    expect(screen.getByText(/safe to execute/i)).toBeInTheDocument();
  });

  it("approval and handoff behavior depend on validation state", async () => {
    const api = buildApi();
    const user = userEvent.setup();

    const firstView = render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    const approveButton = await screen.findByRole("button", { name: /approve plan/i });
    const handoffButton = screen.getByRole("button", { name: /create jira epic \+ tickets/i });

    expect(approveButton).toBeDisabled();
    expect(handoffButton).toBeDisabled();
    firstView.unmount();

    const validApi = buildApi({
      generatePlan: vi.fn().mockResolvedValue({
        ...draftPlan,
        validation_result: {
          ...draftPlan.validation_result!,
          is_valid: true,
          errors: [],
        },
      }),
    });

    render(<PlannerWorkspace apiClient={validApi} />);
    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    const enabledApproveButton = await screen.findByRole("button", { name: /approve plan/i });
    expect(enabledApproveButton).toBeEnabled();

    await user.click(screen.getByRole("checkbox", { name: /accept validation warnings/i }));
    await user.click(screen.getByRole("button", { name: /run jira dry-run/i }));
    await user.click(enabledApproveButton);

    await waitFor(() => expect(validApi.approvePlan).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: /create jira epic \+ tickets/i }));

    await waitFor(() => expect(validApi.handoffPlan).toHaveBeenCalledTimes(1));
    expect(validApi.dryRunPlan).toHaveBeenCalledWith(
      "CTR",
      expect.objectContaining({ sprint_name: "Sprint 18" }),
      expect.objectContaining({ acceptWarnings: true })
    );
  });

  it("marks validation pending after generated plan edits", async () => {
    const api = buildApi({
      generatePlan: vi.fn().mockResolvedValue({
        ...draftPlan,
        validation_result: {
          ...draftPlan.validation_result!,
          is_valid: true,
          errors: [],
          warnings: [],
        },
      }),
    });
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));
    await user.clear(await screen.findByLabelText(/TASK-1 summary/i));
    await user.type(screen.getByLabelText(/TASK-1 summary/i), "Updated planning workspace");

    expect(await screen.findByText(/validation pending/i)).toBeInTheDocument();
    expect(screen.queryByText(/validation ready/i)).not.toBeInTheDocument();
  });
});
