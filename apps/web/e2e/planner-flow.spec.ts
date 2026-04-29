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

const draftPlan = {
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
    is_valid: true,
    errors: [],
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

test("user generates a plan, validates it, dry-runs Jira, approves, and hands off", async ({ page }) => {
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
  await page.route("**/api/v1/jira/dry-run", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
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
        validation_warnings: draftPlan.validation_result.warnings,
        estimated_jira_objects: 2,
        safe_to_execute: true,
        sync_state: {
          idempotency_key: "CTR-abc123",
          project_key: "CTR",
          status: "DRY_RUN_PASSED",
          epic_key: null,
          child_issue_keys: {},
          validation_errors: [],
          validation_warnings: draftPlan.validation_result.warnings,
          last_error: null,
        },
      }),
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
      }),
    });
  });

  await page.goto("/demo");
  await page.getByRole("button", { name: /load sample data/i }).click();
  await expect(page.getByLabel(/sprint name/i)).toHaveValue("Sprint 18");
  await expect(page.getByLabel(/sprint goal/i)).toHaveValue("Ship the Contour MVP flow");

  await page.getByRole("button", { name: /generate draft plan/i }).click();
  await expect(page.getByText(/validation warnings/i)).toBeVisible();

  await page.getByRole("checkbox", { name: /accept validation warnings/i }).check();
  await page.getByRole("button", { name: /run jira dry-run/i }).click();
  await expect(page.getByText(/Jira dry-run preview/i)).toBeVisible();
  await expect(page.getByText(/safe to execute/i)).toBeVisible();

  await page.getByRole("button", { name: /approve plan/i }).click();
  await expect(page.getByText(/ready for jira handoff/i)).toBeVisible();

  await page.getByRole("button", { name: /create jira epic \+ tickets/i }).click();
  await expect(page.getByText(/Jira epic created/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /open epic in jira/i })).toHaveAttribute(
    "href",
    "https://example.atlassian.net/browse/CTR-900"
  );
  await expect(page.getByText("CTR-901")).toBeVisible();
});
