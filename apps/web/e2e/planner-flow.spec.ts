import { expect, test } from "@playwright/test";

const employees = [
  {
    id: "emp-avery",
    name: "Avery",
    role: "Frontend Engineer",
    skills: ["frontend", "react", "ui"],
    capacity_points: 8,
    jira_account_id: "acct-avery",
  },
];

const sampleRequest = {
  sprint_name: "Sprint 18",
  goal: "Ship the Contour MVP flow",
  tasks: [
    {
      text: "Build the planning workspace for the web app.",
      owner_hint: "Avery",
    },
  ],
};

const draftPlan = {
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

test("happy path from sample intake to Jira handoff", async ({ page }) => {
  await page.route("**/api/v1/employees", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(employees),
    });
  });
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

  await page.getByRole("button", { name: /create jira epic \+ tickets/i }).click();
  await expect(page.getByText(/Jira epic created/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /open epic in jira/i })).toHaveAttribute(
    "href",
    "https://example.atlassian.net/browse/CTR-900"
  );
  await expect(page.getByText("CTR-901")).toBeVisible();
});
