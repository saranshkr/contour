from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import CapacitySummary, EnrichedBacklogItem, MemberCapacitySummary, SprintPlan, SprintRequest
from contour.orchestrator import approve_plan, create_plan_epic, plan_sprint
from contour.services.llm import LLMService


class FakeLLMService:
    def __init__(self, enriched_items: list[EnrichedBacklogItem], proposal: dict):
        self._enriched_items = enriched_items
        self._proposal = proposal

    def enrich_backlog(self, request: SprintRequest) -> list[EnrichedBacklogItem]:
        return self._enriched_items

    def propose_plan(self, request: SprintRequest, enriched_items: list[EnrichedBacklogItem]) -> dict:
        return self._proposal


class FakeJiraClient:
    def __init__(self):
        self.base_url = "https://example.atlassian.net"
        self.posts: list[dict] = []

    def get(self, path: str, **params):
        if path.endswith("/issuetypes"):
            return {"issueTypes": [{"id": "10000", "name": "Epic"}]}
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
        if path == "/rest/api/3/field":
            return [
                {"id": "summary", "name": "Summary", "schema": {"type": "string"}},
                {"id": "customfield_10011", "name": "Epic Name", "schema": {"type": "string"}},
                {"id": "description", "name": "Description", "schema": {"type": "string"}},
                {"id": "labels", "name": "Labels", "schema": {"type": "array"}},
                {"id": "priority", "name": "Priority", "schema": {"type": "priority"}},
                {"id": "reporter", "name": "Reporter", "schema": {"type": "user"}},
            ]
        if path == "/rest/api/3/myself":
            return {"accountId": "acct-123"}
        raise AssertionError(f"Unexpected GET path {path}")

    def post(self, path: str, payload: dict):
        self.posts.append(payload)
        return {"key": "CTR-900"}


def build_request() -> SprintRequest:
    return SprintRequest(
        sprint_name="Sprint 18",
        goal="Ship the Contour MVP flow",
        backlog_items=[
            {
                "id": "CTR-1",
                "title": "Create intake screen",
                "description": "Build the web intake flow for sprint planning.",
                "priority": "High",
                "labels": ["frontend"],
            },
            {
                "id": "CTR-2",
                "title": "Create Jira handoff",
                "description": "Build the approved sprint handoff integration.",
                "priority": "High",
                "labels": ["jira"],
            },
        ],
        team_members=[
            {
                "name": "Avery",
                "role": "Frontend Engineer",
                "skills": ["frontend", "react"],
                "capacity_points": 5,
            },
            {
                "name": "Jordan",
                "role": "Platform Engineer",
                "skills": ["jira", "python"],
                "capacity_points": 3,
            },
        ],
    )


class OrchestratorTests(unittest.TestCase):
    def test_plan_sprint_repairs_over_capacity(self) -> None:
        request = build_request()
        enriched_items = [
            EnrichedBacklogItem(
                id="CTR-1",
                title="Create intake screen",
                description="Build the web intake flow for sprint planning.",
                priority="High",
                labels=["frontend"],
                estimated_points=5,
                required_skills=["frontend"],
                ambiguity_flags=[],
                dependency_signals=[],
                analysis_confidence=0.9,
            ),
            EnrichedBacklogItem(
                id="CTR-2",
                title="Create Jira handoff",
                description="Build the approved sprint handoff integration.",
                priority="High",
                labels=["jira"],
                estimated_points=5,
                required_skills=["jira"],
                ambiguity_flags=[],
                dependency_signals=[],
                analysis_confidence=0.85,
            ),
        ]
        fake_llm = FakeLLMService(
            enriched_items=enriched_items,
            proposal={
                "selected_items": [
                    {
                        "id": "CTR-1",
                        "recommended_assignee": "Avery",
                        "alternative_assignees": ["Jordan"],
                        "selection_rationale": "High value item",
                        "assignment_rationale": "Frontend match",
                    },
                    {
                        "id": "CTR-2",
                        "recommended_assignee": "Jordan",
                        "alternative_assignees": ["Avery"],
                        "selection_rationale": "High value item",
                        "assignment_rationale": "Platform match",
                    },
                ],
                "deferred_ids": [],
                "risks": [],
            },
        )

        plan = plan_sprint(request, llm_service=fake_llm)

        self.assertEqual(plan.approval_state, "draft")
        self.assertEqual(len(plan.selected_items), 1)
        self.assertEqual(len(plan.deferred_items), 1)
        self.assertTrue(all(item.recommended_assignee for item in plan.selected_items))
        self.assertIn("capacity", {risk.category for risk in plan.risks})

    def test_plan_sprint_with_fallback_flags_ambiguity_and_dependency_risks(self) -> None:
        request = SprintRequest(
            sprint_name="Sprint 19",
            goal="Validate planner warnings",
            backlog_items=[
                {
                    "id": "CTR-3",
                    "title": "Investigate rollout",
                    "description": "TBD rollout steps depend on API migration?",
                    "priority": "High",
                    "dependencies": ["CTR-1"],
                }
            ],
            team_members=[
                {
                    "name": "Jordan",
                    "role": "Backend Engineer",
                    "skills": ["backend", "api", "migration"],
                    "capacity_points": 8,
                }
            ],
        )

        plan = plan_sprint(request, llm_service=LLMService(prefer_llm=False))

        categories = {risk.category for risk in plan.risks}
        self.assertIn("ambiguity", categories)
        self.assertIn("dependency", categories)

    def test_create_plan_epic_requires_approval(self) -> None:
        draft_plan = SprintPlan(
            sprint_name="Sprint 18",
            goal="Ship the Contour MVP flow",
            selected_items=[],
            deferred_items=[],
            capacity_summary=CapacitySummary(
                total_capacity_points=8,
                selected_points=0,
                remaining_points=8,
                allocations=[
                    MemberCapacitySummary(
                        member_name="Avery",
                        capacity_points=8,
                        assigned_points=0,
                        remaining_points=8,
                    )
                ],
            ),
            risks=[],
            approval_state="draft",
        )

        with self.assertRaises(ValueError):
            create_plan_epic("CTR", draft_plan, jira_client=FakeJiraClient())

    def test_create_plan_epic_formats_approved_plan(self) -> None:
        request = build_request()
        plan = plan_sprint(request, llm_service=LLMService(prefer_llm=False))
        approved_plan = approve_plan(plan)
        jira = FakeJiraClient()

        created_key = create_plan_epic("CTR", approved_plan, jira_client=jira)

        self.assertEqual(created_key, "CTR-900")
        self.assertEqual(len(jira.posts), 1)
        fields = jira.posts[0]["fields"]
        self.assertEqual(fields["project"], {"key": "CTR"})
        self.assertEqual(fields["issuetype"], {"name": "Epic"})
        self.assertEqual(fields["reporter"], {"id": "acct-123"})
        self.assertTrue(fields["summary"].startswith("Sprint 18"))
        self.assertEqual(fields["customfield_10011"], "Sprint 18")
        self.assertIn("Selected sprint items:", fields["description"])
        self.assertIn("Planning risks:", fields["description"])
        self.assertIn("contour", fields["labels"])


if __name__ == "__main__":
    unittest.main()
