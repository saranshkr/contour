import { expect, test } from "@playwright/test";

const sampleRequest = {
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

const draftPlan = {
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

test("happy path from sample intake to Jira handoff", async ({ page }) => {
  await page.route("**/api/v1/sample-request", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(sampleRequest),
    });
  });
  await page.route("**/api/v1/plans/generate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(draftPlan),
    });
  });
  await page.route("**/api/v1/plans/approve", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...draftPlan,
        approval_state: "approved",
      }),
    });
  });
  await page.route("**/api/v1/jira/handoff", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        key: "CTR-900",
        url: "https://example.atlassian.net/browse/CTR-900",
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /load sample data/i }).click();
  await expect(page.getByLabel(/sprint name/i)).toHaveValue("Sprint 18");
  await expect(page.getByLabel(/sprint goal/i)).toHaveValue("Ship the Contour MVP flow");

  await page.getByRole("button", { name: /generate draft plan/i }).click();
  await expect(page.getByText(/Build planning workspace/i)).toBeVisible();

  await page.getByRole("button", { name: /approve plan/i }).click();
  await expect(page.getByText("Ready for Jira handoff", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /create jira plan epic/i }).click();
  await expect(page.getByText(/Jira epic created/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /open in jira/i })).toHaveAttribute(
    "href",
    "https://example.atlassian.net/browse/CTR-900"
  );
});
