from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import (
    CapacitySummary,
    EngineerProfile,
    MemberCapacitySummary,
    PlanItem,
    SprintPlan,
)
from contour.services.constraint_validator import validate_sprint_plan


def build_engineers() -> list[EngineerProfile]:
    return [
        EngineerProfile(
            id="emp-1",
            name="Avery",
            role="Frontend Engineer",
            skills=["frontend", "react"],
            capacity_points=5,
            jira_account_id="acct-1",
        ),
        EngineerProfile(
            id="emp-2",
            name="Jordan",
            role="Backend Engineer",
            skills=["backend", "python"],
            capacity_points=5,
            jira_account_id="acct-2",
        ),
    ]


def build_plan_item(**overrides) -> PlanItem:
    payload = {
        "task_id": "TASK-1",
        "source_index": 0,
        "task_text": "Build the intake flow.",
        "owner_hint": "Avery",
        "backlog_item_id": "BL-1",
        "title": "Build intake flow",
        "description": "Create the intake experience.",
        "acceptance_criteria": ["User can submit a sprint goal."],
        "priority": "high",
        "jira_issue_type": "Story",
        "status": "todo",
        "story_points": 5,
        "required_skills": ["frontend"],
        "estimation_rationale": "High priority UI work.",
        "recommended_assignee": "Avery",
        "recommended_assignee_account_id": "acct-1",
        "alternative_assignees": ["Jordan"],
        "assignment_status": "assigned",
        "selection_rationale": "Included in the sprint.",
        "assignment_rationale": "Best fit.",
        "risk_flags": [],
    }
    payload.update(overrides)
    return PlanItem(**payload)


def build_plan(items: list[PlanItem]) -> SprintPlan:
    total_assigned = sum(item.story_points for item in items if item.recommended_assignee)
    return SprintPlan(
        sprint_name="Sprint 18",
        goal="Ship the planning flow",
        plan_items=items,
        capacity_summary=CapacitySummary(
            total_capacity_points=10,
            assigned_points=total_assigned,
            unassigned_points=sum(item.story_points for item in items if item.recommended_assignee is None),
            remaining_points=10 - total_assigned,
            allocations=[
                MemberCapacitySummary(
                    member_name="Avery",
                    capacity_points=5,
                    assigned_points=min(total_assigned, 5),
                    remaining_points=5 - min(total_assigned, 5),
                ),
                MemberCapacitySummary(
                    member_name="Jordan",
                    capacity_points=5,
                    assigned_points=max(total_assigned - 5, 0),
                    remaining_points=5 - max(total_assigned - 5, 0),
                ),
            ],
        ),
        risks=[],
        approval_state="draft",
    )


class ConstraintValidatorTests(unittest.TestCase):
    def test_valid_sprint_plan_passes_validation(self) -> None:
        result = validate_sprint_plan(build_plan([build_plan_item()]), build_engineers())

        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    def test_overloaded_sprint_fails_capacity_validation(self) -> None:
        result = validate_sprint_plan(
            build_plan(
                [
                    build_plan_item(task_id="TASK-1", story_points=5),
                    build_plan_item(
                        task_id="TASK-2",
                        backlog_item_id="BL-2",
                        title="Add review drawer",
                        story_points=8,
                        recommended_assignee="Avery",
                        recommended_assignee_account_id="acct-1",
                    ),
                ]
            ),
            build_engineers(),
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(any(error.code == "total_points_exceed_capacity" for error in result.errors))

    def test_malformed_task_fails_validation(self) -> None:
        malformed = build_plan_item()
        malformed.title = " "
        malformed.description = " "
        result = validate_sprint_plan(
            build_plan([malformed]),
            build_engineers(),
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(any(error.code == "missing_task_title" for error in result.errors))
        self.assertTrue(any(error.code == "missing_task_description" for error in result.errors))

    def test_invalid_owner_assignment_is_caught(self) -> None:
        result = validate_sprint_plan(
            build_plan(
                [
                    build_plan_item(
                        recommended_assignee="Pat",
                        recommended_assignee_account_id="acct-unknown",
                    )
                ]
            ),
            build_engineers(),
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(any(error.code == "unknown_owner" for error in result.errors))

    def test_duplicate_backlog_item_ids_are_caught(self) -> None:
        result = validate_sprint_plan(
            build_plan(
                [
                    build_plan_item(task_id="TASK-1", backlog_item_id="BL-1"),
                    build_plan_item(task_id="TASK-2", backlog_item_id="BL-1"),
                ]
            ),
            build_engineers(),
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(any(error.code == "duplicate_backlog_item_id" for error in result.errors))


if __name__ == "__main__":
    unittest.main()
