from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import (
    BacklogItemInput,
    CapacitySummary,
    EnrichedBacklogItem,
    MemberCapacitySummary,
    SprintPlan,
    SprintRequest,
    TeamMemberInput,
)


class ModelValidationTests(unittest.TestCase):
    def test_backlog_item_requires_title(self) -> None:
        with self.assertRaises(ValidationError):
            BacklogItemInput(
                id="CTR-1",
                title="",
                description="Implement the intake flow.",
                priority="High",
            )

    def test_team_member_requires_skills(self) -> None:
        with self.assertRaises(ValidationError):
            TeamMemberInput(
                name="Avery",
                role="Engineer",
                skills=[],
                capacity_points=5,
            )

    def test_sprint_request_requires_capacity_points(self) -> None:
        with self.assertRaises(ValidationError):
            SprintRequest(
                sprint_name="Sprint 1",
                goal="Ship MVP planning flow",
                backlog_items=[
                    {
                        "id": "CTR-1",
                        "title": "Create intake screen",
                        "description": "Build the first planning form.",
                        "priority": "High",
                    }
                ],
                team_members=[
                    {
                        "name": "Avery",
                        "role": "Engineer",
                        "skills": ["frontend"],
                    }
                ],
            )

    def test_backlog_item_rejects_self_dependency(self) -> None:
        with self.assertRaises(ValidationError):
            BacklogItemInput(
                id="CTR-1",
                title="Create intake screen",
                description="Build the first planning form.",
                priority="High",
                dependencies=["CTR-1"],
            )

    def test_sprint_request_rejects_duplicate_backlog_ids(self) -> None:
        with self.assertRaises(ValidationError):
            SprintRequest(
                sprint_name="Sprint 1",
                goal="Ship MVP planning flow",
                backlog_items=[
                    {
                        "id": "CTR-1",
                        "title": "Create intake screen",
                        "description": "Build the first planning form.",
                        "priority": "High",
                    },
                    {
                        "id": "ctr-1",
                        "title": "Create review screen",
                        "description": "Build the review form.",
                        "priority": "Medium",
                    },
                ],
                team_members=[
                    {
                        "name": "Avery",
                        "role": "Engineer",
                        "skills": ["frontend"],
                        "capacity_points": 5,
                    }
                ],
            )

    def test_sprint_request_rejects_duplicate_team_member_names(self) -> None:
        with self.assertRaises(ValidationError):
            SprintRequest(
                sprint_name="Sprint 1",
                goal="Ship MVP planning flow",
                backlog_items=[
                    {
                        "id": "CTR-1",
                        "title": "Create intake screen",
                        "description": "Build the first planning form.",
                        "priority": "High",
                    }
                ],
                team_members=[
                    {
                        "name": "Avery",
                        "role": "Engineer",
                        "skills": ["frontend"],
                        "capacity_points": 5,
                    },
                    {
                        "name": "avery",
                        "role": "Designer",
                        "skills": ["ui"],
                        "capacity_points": 3,
                    },
                ],
            )

    def test_capacity_summary_rejects_inconsistent_member_totals(self) -> None:
        with self.assertRaises(ValidationError):
            MemberCapacitySummary(
                member_name="Avery",
                capacity_points=8,
                assigned_points=5,
                remaining_points=1,
            )

    def test_sprint_plan_rejects_selected_and_deferred_overlap(self) -> None:
        item = EnrichedBacklogItem(
            id="CTR-1",
            title="Create intake screen",
            description="Build the first planning form.",
            priority="High",
            estimated_points=3,
            required_skills=["frontend"],
            ambiguity_flags=[],
            dependency_signals=[],
            analysis_confidence=0.9,
        )

        with self.assertRaises(ValidationError):
            SprintPlan(
                sprint_name="Sprint 1",
                goal="Ship MVP planning flow",
                selected_items=[
                    {
                        **item.model_dump(),
                        "recommended_assignee": "Avery",
                        "alternative_assignees": ["Jordan"],
                        "selection_rationale": "High priority and fits the sprint.",
                        "assignment_rationale": "Best skill match.",
                    }
                ],
                deferred_items=[item],
                capacity_summary=CapacitySummary(
                    total_capacity_points=8,
                    selected_points=3,
                    remaining_points=5,
                    allocations=[
                        MemberCapacitySummary(
                            member_name="Avery",
                            capacity_points=8,
                            assigned_points=3,
                            remaining_points=5,
                        )
                    ],
                ),
                risks=[],
                approval_state="draft",
            )
