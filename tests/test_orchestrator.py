from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import EmployeeRecord, NormalizedTask, SprintPlan, SprintRequest
from contour.orchestrator import approve_plan, create_plan_epic, dry_run_plan_handoff, plan_sprint
from contour.services.jira_sync_store import JiraSyncStore


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
                "id": "BL-1",
                "text": "Build the planning workspace for the web app.",
                "owner_hint": "Avery",
                "acceptance_criteria": ["Workspace loads sample sprint data."],
            },
            {
                "id": "BL-2",
                "text": "Create the Jira handoff integration.",
                "owner_hint": "Jordan",
                "acceptance_criteria": ["Dry-run preview is available before issue creation."],
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
            capacity_points=5,
            jira_account_id="acct-jordan",
        ),
    ]


def build_normalized_items(request: SprintRequest) -> list[NormalizedTask]:
    return [
        NormalizedTask(
            task_id="TASK-1",
            source_index=0,
            task_text=request.tasks[0].text or "",
            owner_hint="Avery",
            backlog_item_id="BL-1",
            title="Build planning workspace",
            description="Create the intake and review UI for Contour.",
            acceptance_criteria=["Workspace loads sample sprint data."],
            priority="high",
            jira_issue_type="Story",
            story_points=5,
            required_skills=["frontend"],
            estimation_rationale="High-priority UI work.",
        ),
        NormalizedTask(
            task_id="TASK-2",
            source_index=1,
            task_text=request.tasks[1].text or "",
            owner_hint="Jordan",
            backlog_item_id="BL-2",
            title="Create Jira handoff",
            description="Build the approved sprint handoff integration.",
            acceptance_criteria=["Dry-run preview is available before issue creation."],
            priority="medium",
            jira_issue_type="Task",
            story_points=3,
            required_skills=["jira"],
            estimation_rationale="Integration work with Jira.",
        ),
    ]


class OrchestratorTests(unittest.TestCase):
    def test_dry_run_returns_payload_preview_without_creating_issues(self) -> None:
        request = build_request()
        fake_llm = FakeLLMService(build_normalized_items(request))
        fake_jira = FakeJiraClient()

        with patch("contour.orchestrator.build_employee_roster", return_value=build_roster()):
            plan = plan_sprint(request, llm_service=fake_llm)

        with tempfile.TemporaryDirectory() as temp_dir:
            response = dry_run_plan_handoff(
                project_key="CTR",
                plan=plan,
                jira_client=fake_jira,
                sync_store=JiraSyncStore(Path(temp_dir) / "sync.db"),
            )

        self.assertTrue(response.safe_to_execute)
        self.assertEqual(response.estimated_jira_objects, 3)
        self.assertEqual(len(fake_jira.posts), 0)
        self.assertEqual(response.sync_state.status.value, "DRY_RUN_PASSED")

    def test_dry_run_requires_explicit_warning_acceptance(self) -> None:
        request = build_request()
        fake_llm = FakeLLMService(build_normalized_items(request))
        fake_jira = FakeJiraClient()

        with patch("contour.orchestrator.build_employee_roster", return_value=build_roster()):
            plan = plan_sprint(request, llm_service=fake_llm)

        plan.plan_items[0].acceptance_criteria = []
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JiraSyncStore(Path(temp_dir) / "sync.db")
            blocked = dry_run_plan_handoff(
                project_key="CTR",
                plan=plan,
                jira_client=fake_jira,
                sync_store=store,
            )
            accepted = dry_run_plan_handoff(
                project_key="CTR",
                plan=plan,
                jira_client=fake_jira,
                sync_store=store,
                accept_warnings=True,
            )

        self.assertFalse(blocked.safe_to_execute)
        self.assertIn("accepted", blocked.sync_state.last_error or "")
        self.assertTrue(accepted.safe_to_execute)

    def test_idempotency_prevents_duplicate_jira_issue_creation(self) -> None:
        request = build_request()
        fake_llm = FakeLLMService(build_normalized_items(request))
        fake_jira = FakeJiraClient()

        with patch("contour.orchestrator.build_employee_roster", return_value=build_roster()):
            draft_plan = plan_sprint(request, llm_service=fake_llm)
            approved_plan = approve_plan(draft_plan, engineers=build_roster())

        with tempfile.TemporaryDirectory() as temp_dir:
            store = JiraSyncStore(Path(temp_dir) / "sync.db")
            first_result = create_plan_epic(
                "CTR",
                approved_plan,
                jira_client=fake_jira,
                engineers=build_roster(),
                sync_store=store,
            )
            second_result = create_plan_epic(
                "CTR",
                approved_plan,
                jira_client=fake_jira,
                engineers=build_roster(),
                sync_store=store,
            )

        self.assertEqual(first_result.key, second_result.key)
        self.assertEqual(len(first_result.issues), len(second_result.issues))
        self.assertEqual(len(fake_jira.posts), 3)


if __name__ == "__main__":
    unittest.main()
