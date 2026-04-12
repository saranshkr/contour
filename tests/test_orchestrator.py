from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import EmployeeRecord, NormalizedTask, SprintPlan, SprintRequest
from contour.orchestrator import approve_plan, create_plan_epic, plan_sprint


class FakeLLMService:
    def __init__(self, normalized_items: list[NormalizedTask]):
        self._normalized_items = normalized_items

    def normalize_tasks(
        self,
        request: SprintRequest,
        employees: list[EmployeeRecord],
    ) -> list[NormalizedTask]:
        return self._normalized_items


class FakeJiraClient:
    def __init__(self):
        self.base_url = "https://example.atlassian.net"
        self.posts: list[dict] = []

    def get(self, path: str, **params):
        if path.endswith("/issuetypes"):
            return {
                "issueTypes": [
                    {"id": "10000", "name": "Epic"},
                    {"id": "10001", "name": "Story"},
                    {"id": "10002", "name": "Task"},
                ]
            }
        if path.endswith("/issuetypes/10000"):
            return {
                "fields": {
                    "summary": {"required": True, "name": "Summary"},
                    "customfield_10011": {"required": True, "name": "Epic Name"},
                    "description": {"required": True, "name": "Description"},
                    "labels": {"required": False, "name": "Labels"},
                    "priority": {"required": False, "name": "Priority"},
                    "reporter": {"required": False, "name": "Reporter"},
                }
            }
        if path.endswith("/issuetypes/10001") or path.endswith("/issuetypes/10002"):
            return {
                "fields": {
                    "summary": {"required": True, "name": "Summary"},
                    "description": {"required": True, "name": "Description"},
                    "labels": {"required": False, "name": "Labels"},
                    "priority": {"required": False, "name": "Priority"},
                    "assignee": {"required": False, "name": "Assignee"},
                    "parent": {"required": False, "name": "Parent"},
                    "customfield_10016": {"required": False, "name": "Story point estimate"},
                    "reporter": {"required": False, "name": "Reporter"},
                }
            }
        if path == "/rest/api/3/field":
            return [
                {"id": "summary", "name": "Summary", "schema": {"type": "string"}},
                {"id": "customfield_10011", "name": "Epic Name", "schema": {"type": "string"}},
                {"id": "description", "name": "Description", "schema": {"type": "string"}},
                {"id": "labels", "name": "Labels", "schema": {"type": "array"}},
                {"id": "priority", "name": "Priority", "schema": {"type": "priority"}},
                {"id": "reporter", "name": "Reporter", "schema": {"type": "user"}},
                {"id": "assignee", "name": "Assignee", "schema": {"type": "user"}},
                {"id": "parent", "name": "Parent", "schema": {"type": "issuelink"}},
                {"id": "customfield_10016", "name": "Story point estimate", "schema": {"type": "number"}},
            ]
        if path == "/rest/api/3/myself":
            return {"accountId": "acct-system"}
        raise AssertionError(f"Unexpected GET path {path}")

    def post(self, path: str, payload: dict):
        self.posts.append(payload)
        return {"key": f"CTR-{900 + len(self.posts) - 1}"}


def build_request() -> SprintRequest:
    return SprintRequest(
        sprint_name="Sprint 18",
        goal="Ship the Contour MVP flow",
        tasks=[
            {
                "text": "Build the planning workspace for the web app.",
                "owner_hint": "Avery",
            },
            {
                "text": "Create the Jira handoff integration.",
                "owner_hint": "Jordan",
            },
        ],
    )


def build_roster() -> list[EmployeeRecord]:
    return [
        EmployeeRecord(
            id="emp-avery",
            name="Avery",
            role="Frontend Engineer",
            skills=["frontend", "react"],
            capacity_points=5,
            jira_account_id="acct-avery",
        ),
        EmployeeRecord(
            id="emp-jordan",
            name="Jordan",
            role="Platform Engineer",
            skills=["jira", "python"],
            capacity_points=3,
            jira_account_id="acct-jordan",
        ),
    ]


class OrchestratorTests(unittest.TestCase):
    def test_plan_sprint_uses_story_point_capacity_and_leaves_overflow_unassigned(self) -> None:
        request = build_request()
        fake_llm = FakeLLMService(
            normalized_items=[
                NormalizedTask(
                    task_id="TASK-1",
                    source_index=0,
                    task_text=request.tasks[0].text,
                    owner_hint="Avery",
                    title="Build planning workspace",
                    description="Create the intake and review UI for Contour.",
                    priority="high",
                    jira_issue_type="Story",
                    story_points=5,
                    required_skills=["frontend"],
                    estimation_rationale="High-priority UI work.",
                ),
                NormalizedTask(
                    task_id="TASK-2",
                    source_index=1,
                    task_text=request.tasks[1].text,
                    owner_hint="Jordan",
                    title="Create Jira handoff",
                    description="Build the approved sprint handoff integration.",
                    priority="high",
                    jira_issue_type="Task",
                    story_points=5,
                    required_skills=["jira"],
                    estimation_rationale="Integration work with Jira.",
                ),
            ]
        )

        with patch("contour.orchestrator.build_employee_roster", return_value=build_roster()):
            plan = plan_sprint(request, llm_service=fake_llm)

        self.assertEqual(plan.approval_state, "draft")
        self.assertEqual(len(plan.plan_items), 2)
        self.assertEqual(plan.plan_items[0].assignment_status, "assigned")
        self.assertEqual(plan.plan_items[0].recommended_assignee, "Avery")
        self.assertEqual(plan.plan_items[1].assignment_status, "unassigned_capacity")
        self.assertIsNone(plan.plan_items[1].recommended_assignee)
        self.assertEqual(plan.capacity_summary.assigned_points, 5)
        self.assertEqual(plan.capacity_summary.unassigned_points, 5)

    def test_plan_sprint_leaves_medium_priority_skill_gap_unassigned(self) -> None:
        request = SprintRequest(
            sprint_name="Sprint 19",
            goal="Ship backend handoff",
            tasks=[{"text": "Create a design system refresh for the landing page."}],
        )
        fake_llm = FakeLLMService(
            normalized_items=[
                NormalizedTask(
                    task_id="TASK-1",
                    source_index=0,
                    task_text=request.tasks[0].text,
                    title="Refresh design system",
                    description="Refresh the landing page design system.",
                    priority="medium",
                    jira_issue_type="Story",
                    story_points=3,
                    required_skills=["design"],
                    estimation_rationale="Moderate design-heavy work.",
                )
            ]
        )
        roster = [
            EmployeeRecord(
                id="emp-jordan",
                name="Jordan",
                role="Backend Engineer",
                skills=["backend"],
                capacity_points=5,
                jira_account_id="acct-jordan",
            )
        ]

        with patch("contour.orchestrator.build_employee_roster", return_value=roster):
            plan = plan_sprint(request, llm_service=fake_llm)

        self.assertEqual(plan.plan_items[0].assignment_status, "unassigned_skill_gap")
        self.assertIsNone(plan.plan_items[0].recommended_assignee)

    def test_plan_sprint_assigns_high_priority_skill_gap_to_best_match(self) -> None:
        request = SprintRequest(
            sprint_name="Sprint 20",
            goal="Unblock urgent work",
            tasks=[{"text": "Urgent design escalation for executive review."}],
        )
        fake_llm = FakeLLMService(
            normalized_items=[
                NormalizedTask(
                    task_id="TASK-1",
                    source_index=0,
                    task_text=request.tasks[0].text,
                    title="Handle urgent design escalation",
                    description="Address the urgent executive design escalation.",
                    priority="high",
                    jira_issue_type="Task",
                    story_points=3,
                    required_skills=["design"],
                    estimation_rationale="Urgent work requiring fast turnaround.",
                )
            ]
        )
        roster = [
            EmployeeRecord(
                id="emp-jordan",
                name="Jordan",
                role="Generalist Engineer",
                skills=["backend"],
                capacity_points=5,
                jira_account_id="acct-jordan",
            )
        ]

        with patch("contour.orchestrator.build_employee_roster", return_value=roster):
            plan = plan_sprint(request, llm_service=fake_llm)

        self.assertEqual(plan.plan_items[0].assignment_status, "assigned_with_skill_gap")
        self.assertEqual(plan.plan_items[0].recommended_assignee, "Jordan")

    def test_approve_plan_repairs_manual_over_capacity_assignment(self) -> None:
        request = build_request()
        fake_llm = FakeLLMService(
            normalized_items=[
                NormalizedTask(
                    task_id="TASK-1",
                    source_index=0,
                    task_text=request.tasks[0].text,
                    owner_hint="Avery",
                    title="Build planning workspace",
                    description="Create the intake and review UI for Contour.",
                    priority="high",
                    jira_issue_type="Story",
                    story_points=5,
                    required_skills=["frontend"],
                    estimation_rationale="High-priority UI work.",
                ),
                NormalizedTask(
                    task_id="TASK-2",
                    source_index=1,
                    task_text=request.tasks[1].text,
                    owner_hint="Jordan",
                    title="Create Jira handoff",
                    description="Build the approved sprint handoff integration.",
                    priority="medium",
                    jira_issue_type="Task",
                    story_points=3,
                    required_skills=["jira"],
                    estimation_rationale="Moderate integration work.",
                ),
            ]
        )

        with patch("contour.orchestrator.build_employee_roster", return_value=build_roster()):
            draft_plan = plan_sprint(request, llm_service=fake_llm)
            edited_item = draft_plan.plan_items[1].model_copy(
                update={
                    "story_points": 5,
                    "recommended_assignee": "Avery",
                    "recommended_assignee_account_id": "acct-avery",
                    "assignment_status": "assigned",
                }
            )
            edited_plan = draft_plan.model_copy(
                update={"plan_items": [draft_plan.plan_items[0], edited_item]}
            )
            approved_plan = approve_plan(edited_plan)

        self.assertEqual(approved_plan.approval_state, "approved")
        self.assertEqual(approved_plan.plan_items[1].assignment_status, "unassigned_capacity")
        self.assertIsNone(approved_plan.plan_items[1].recommended_assignee)

    def test_create_plan_epic_requires_approval(self) -> None:
        draft_plan = SprintPlan(
            sprint_name="Sprint 18",
            goal="Ship the Contour MVP flow",
            plan_items=[],
            capacity_summary={
                "total_capacity_points": 8,
                "assigned_points": 0,
                "unassigned_points": 0,
                "remaining_points": 8,
                "allocations": [
                    {
                        "member_name": "Avery",
                        "capacity_points": 8,
                        "assigned_points": 0,
                        "remaining_points": 8,
                    }
                ],
            },
            risks=[],
            approval_state="draft",
        )

        with self.assertRaises(ValueError):
            create_plan_epic("CTR", draft_plan, jira_client=FakeJiraClient())

    def test_create_plan_epic_creates_epic_and_child_issues(self) -> None:
        request = build_request()
        fake_llm = FakeLLMService(
            normalized_items=[
                NormalizedTask(
                    task_id="TASK-1",
                    source_index=0,
                    task_text=request.tasks[0].text,
                    owner_hint="Avery",
                    title="Build planning workspace",
                    description="Create the intake and review UI for Contour.",
                    priority="high",
                    jira_issue_type="Story",
                    story_points=5,
                    required_skills=["frontend"],
                    estimation_rationale="High-priority UI work.",
                ),
                NormalizedTask(
                    task_id="TASK-2",
                    source_index=1,
                    task_text=request.tasks[1].text,
                    owner_hint="Jordan",
                    title="Create Jira handoff",
                    description="Build the approved sprint handoff integration.",
                    priority="high",
                    jira_issue_type="Task",
                    story_points=5,
                    required_skills=["jira"],
                    estimation_rationale="Integration work with Jira.",
                ),
            ]
        )

        with patch("contour.orchestrator.build_employee_roster", return_value=build_roster()):
            plan = plan_sprint(request, llm_service=fake_llm)
            approved_plan = approve_plan(plan)

        jira = FakeJiraClient()
        result = create_plan_epic("CTR", approved_plan, jira_client=jira)

        self.assertEqual(result.key, "CTR-900")
        self.assertEqual(len(result.issues), 2)
        self.assertEqual(len(jira.posts), 3)

        epic_fields = jira.posts[0]["fields"]
        self.assertEqual(epic_fields["issuetype"], {"name": "Epic"})
        self.assertEqual(epic_fields["reporter"], {"id": "acct-system"})

        first_child_fields = jira.posts[1]["fields"]
        self.assertEqual(first_child_fields["issuetype"], {"name": "Story"})
        self.assertEqual(first_child_fields["assignee"], {"id": "acct-avery"})
        self.assertEqual(first_child_fields["parent"], {"key": "CTR-900"})
        self.assertEqual(first_child_fields["customfield_10016"], 5)

        second_child_fields = jira.posts[2]["fields"]
        self.assertEqual(second_child_fields["issuetype"], {"name": "Task"})
        self.assertEqual(second_child_fields["parent"], {"key": "CTR-900"})
        self.assertNotIn("assignee", second_child_fields)


if __name__ == "__main__":
    unittest.main()
