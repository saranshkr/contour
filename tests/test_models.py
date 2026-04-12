from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import (
    CapacitySummary,
    EmployeeRecord,
    MemberCapacitySummary,
    PlanItem,
    RiskFlag,
    SprintPlan,
    SprintRequest,
    TaskInput,
)


class ModelValidationTests(unittest.TestCase):
    def test_task_input_requires_text(self) -> None:
        with self.assertRaises(ValidationError):
            TaskInput(text="")

    def test_employee_record_requires_jira_account_id(self) -> None:
        with self.assertRaises(ValidationError):
            EmployeeRecord(
                id="emp-1",
                name="Avery",
                role="Engineer",
                skills=["frontend"],
                capacity_points=5,
                jira_account_id="",
            )

    def test_sprint_request_rejects_duplicate_tasks(self) -> None:
        with self.assertRaises(ValidationError):
            SprintRequest(
                sprint_name="Sprint 1",
                goal="Ship MVP planning flow",
                tasks=[
                    {"text": "Build the intake flow."},
                    {"text": "build the intake flow."},
                ],
            )

    def test_plan_item_requires_assignee_for_assigned_status(self) -> None:
        with self.assertRaises(ValidationError):
            PlanItem(
                task_id="TASK-1",
                source_index=0,
                task_text="Build the intake flow.",
                title="Build intake flow",
                description="Create the intake experience.",
                priority="high",
                jira_issue_type="Story",
                story_points=5,
                required_skills=["frontend"],
                estimation_rationale="High priority UI work.",
                recommended_assignee=None,
                recommended_assignee_account_id=None,
                alternative_assignees=["Jordan"],
                assignment_status="assigned",
                selection_rationale="Included in the sprint.",
                assignment_rationale="Best fit.",
                risk_flags=[],
            )

    def test_plan_item_rejects_assignee_on_unassigned_status(self) -> None:
        with self.assertRaises(ValidationError):
            PlanItem(
                task_id="TASK-1",
                source_index=0,
                task_text="Build the intake flow.",
                title="Build intake flow",
                description="Create the intake experience.",
                priority="medium",
                jira_issue_type="Story",
                story_points=3,
                required_skills=["frontend"],
                estimation_rationale="Moderate UI work.",
                recommended_assignee="Avery",
                recommended_assignee_account_id="acct-avery",
                alternative_assignees=["Jordan"],
                assignment_status="unassigned_capacity",
                selection_rationale="Included in the sprint.",
                assignment_rationale="Left unassigned.",
                risk_flags=[],
            )

    def test_capacity_summary_rejects_inconsistent_member_totals(self) -> None:
        with self.assertRaises(ValidationError):
            MemberCapacitySummary(
                member_name="Avery",
                capacity_points=8,
                assigned_points=5,
                remaining_points=1,
            )

    def test_sprint_plan_rejects_duplicate_task_ids(self) -> None:
        risk = RiskFlag(
            severity="medium",
            category="capacity",
            message="Capacity is tight.",
            affected_items=["TASK-1"],
            suggested_action="Rebalance work.",
        )
        item = {
            "task_id": "TASK-1",
            "source_index": 0,
            "task_text": "Build the intake flow.",
            "title": "Build intake flow",
            "description": "Create the intake experience.",
            "priority": "high",
            "jira_issue_type": "Story",
            "story_points": 5,
            "required_skills": ["frontend"],
            "estimation_rationale": "High priority UI work.",
            "recommended_assignee": "Avery",
            "recommended_assignee_account_id": "acct-avery",
            "alternative_assignees": ["Jordan"],
            "assignment_status": "assigned",
            "selection_rationale": "Included in the sprint.",
            "assignment_rationale": "Best fit.",
            "risk_flags": [risk.model_dump()],
        }

        with self.assertRaises(ValidationError):
            SprintPlan(
                sprint_name="Sprint 1",
                goal="Ship MVP planning flow",
                plan_items=[item, {**item, "source_index": 1}],
                capacity_summary=CapacitySummary(
                    total_capacity_points=8,
                    assigned_points=8,
                    unassigned_points=0,
                    remaining_points=0,
                    allocations=[
                        MemberCapacitySummary(
                            member_name="Avery",
                            capacity_points=8,
                            assigned_points=8,
                            remaining_points=0,
                        )
                    ],
                ),
                risks=[],
                approval_state="draft",
            )


if __name__ == "__main__":
    unittest.main()
