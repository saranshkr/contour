from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import BacklogItemInput, SprintRequest, TeamMemberInput


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
