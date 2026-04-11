import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PlannerWorkspace } from "@/components/planner-workspace";
import { PlannerApi } from "@/lib/api";
import {
  JiraHandoffResponse,
  SprintPlan,
  SprintRequest,
} from "@/lib/schemas";

const sampleRequest: SprintRequest = {
  sprint_name: "Sprint 18",
  goal: "Ship the Contour MVP flow",
  backlog_items: [
    {
      id: "CTR-101",
      title: "Build planning workspace",
      description: "Create the intake and review UI for Contour.",
      priority: "High",
      dependencies: [],
      owner_hint: "Avery",
      labels: ["frontend", "ui"],
    },
  ],
  team_members: [
    {
      name: "Avery",
      role: "Frontend Engineer",
      skills: ["frontend", "react", "ui"],
      capacity_points: 8,
    },
  ],
};

const draftPlan: SprintPlan = {
  sprint_name: "Sprint 18",
  goal: "Ship the Contour MVP flow",
  selected_items: [
    {
      id: "CTR-101",
      title: "Build planning workspace",
      description: "Create the intake and review UI for Contour.",
      priority: "High",
      dependencies: [],
      owner_hint: "Avery",
      labels: ["frontend", "ui"],
      estimated_points: 5,
      required_skills: ["frontend", "ui"],
      ambiguity_flags: [],
      dependency_signals: [],
      analysis_confidence: 0.92,
      recommended_assignee: "Avery",
      alternative_assignees: [],
      selection_rationale: "It aligns to the sprint goal and fits within capacity.",
      assignment_rationale: "Avery has the strongest frontend context.",
    },
  ],
  deferred_items: [],
  capacity_summary: {
    total_capacity_points: 8,
    selected_points: 5,
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
};

function buildApi(overrides: Partial<PlannerApi> = {}): PlannerApi {
  return {
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
    expect(screen.getByDisplayValue("Build planning workspace")).toBeInTheDocument();
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
            selected_points: 6,
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

    const handoffButton = await screen.findByRole("button", { name: /create jira plan epic/i });
    expect(handoffButton).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /approve plan/i }));

    await waitFor(() => expect(api.approvePlan).toHaveBeenCalledTimes(1));
    expect(handoffButton).toBeEnabled();

    await user.click(handoffButton);

    await waitFor(() => expect(api.handoffPlan).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Jira epic created/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open in jira/i })).toHaveAttribute("href", jiraResponse.url);
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
