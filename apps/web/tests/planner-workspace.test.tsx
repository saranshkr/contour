import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PlannerWorkspace } from "@/components/planner-workspace";
import { PlannerApi } from "@/lib/api";
import {
  EmployeeRecord,
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
      text: "Build the planning workspace for the web app.",
      owner_hint: "Avery",
    },
  ],
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
      title: "Build planning workspace",
      description: "Create the intake and review UI for Contour.",
      priority: "high",
      jira_issue_type: "Story",
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
  approval_state: "draft",
};

const approvedPlan: SprintPlan = {
  ...draftPlan,
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
    },
  ],
};

function buildApi(overrides: Partial<PlannerApi> = {}): PlannerApi {
  return {
    loadEmployees: vi.fn().mockResolvedValue(employees),
    loadSampleRequest: vi.fn().mockResolvedValue(sampleRequest),
    generatePlan: vi.fn().mockResolvedValue(draftPlan),
    approvePlan: vi.fn().mockResolvedValue(approvedPlan),
    handoffPlan: vi.fn().mockResolvedValue(jiraResponse),
    ...overrides,
  };
}

describe("PlannerWorkspace", () => {
  it("loads sample data into the intake form", async () => {
    const api = buildApi();
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));

    expect(await screen.findByDisplayValue("Sprint 18")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Ship the Contour MVP flow")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Build the planning workspace for the web app.")).toBeInTheDocument();
  });

  it("shows validation errors before generating an invalid draft", async () => {
    const api = buildApi();
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /generate draft plan/i }));

    expect(await screen.findByText(/Sprint name is required/i)).toBeInTheDocument();
    expect(api.generatePlan).not.toHaveBeenCalled();
  });

  it("generates and regenerates the draft plan", async () => {
    const api = buildApi({
      generatePlan: vi
        .fn()
        .mockResolvedValueOnce(draftPlan)
        .mockResolvedValueOnce({
          ...draftPlan,
          capacity_summary: {
            ...draftPlan.capacity_summary,
            assigned_points: 6,
          },
        }),
    });
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    expect(await screen.findByText(/Draft sprint plan generated/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /regenerate draft/i }));

    await waitFor(() => expect(api.generatePlan).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Draft regenerated/i)).toBeInTheDocument();
  });

  it("keeps Jira handoff gated until approval and then completes the handoff", async () => {
    const api = buildApi();
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    const handoffButton = await screen.findByRole("button", { name: /create jira epic \+ tickets/i });
    expect(handoffButton).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /approve plan/i }));

    await waitFor(() => expect(api.approvePlan).toHaveBeenCalledTimes(1));
    expect(handoffButton).toBeEnabled();

    await user.click(handoffButton);

    await waitFor(() => expect(api.handoffPlan).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Jira epic created/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open epic in jira/i })).toHaveAttribute("href", jiraResponse.url);
    expect(screen.getByText(/CTR-901/i)).toBeInTheDocument();
  });

  it("surfaces API errors when draft generation fails", async () => {
    const api = buildApi({
      generatePlan: vi.fn().mockRejectedValue(new Error("Planner service unavailable.")),
    });
    const user = userEvent.setup();

    render(<PlannerWorkspace apiClient={api} />);

    await user.click(screen.getByRole("button", { name: /load sample data/i }));
    await user.click(await screen.findByRole("button", { name: /generate draft plan/i }));

    expect(await screen.findByText(/Planner service unavailable/i)).toBeInTheDocument();
  });
});
