from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.api.main import create_app
from contour.sample_data import build_sample_request


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_sample_request_returns_seed_data(self) -> None:
        response = self.client.get("/api/v1/sample-request")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sprint_name"], "Sprint 18")
        self.assertGreaterEqual(len(payload["tasks"]), 1)

    def test_employee_endpoint_returns_built_in_roster(self) -> None:
        response = self.client.get("/api/v1/employees")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload), 1)
        self.assertIn("jira_account_id", payload[0])

    def test_generate_plan_returns_draft_plan(self) -> None:
        request = build_sample_request().model_dump()

        response = self.client.post("/api/v1/plans/generate", json=request)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["approval_state"], "draft")
        self.assertIn("capacity_summary", payload)
        self.assertIn("plan_items", payload)

    def test_approve_endpoint_marks_plan_as_approved(self) -> None:
        request = build_sample_request().model_dump()
        draft_plan = self.client.post("/api/v1/plans/generate", json=request).json()

        response = self.client.post("/api/v1/plans/approve", json=draft_plan)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["approval_state"], "approved")

    def test_jira_handoff_requires_approval(self) -> None:
        request = build_sample_request().model_dump()
        draft_plan = self.client.post("/api/v1/plans/generate", json=request).json()

        response = self.client.post(
            "/api/v1/jira/handoff",
            json={"project_key": "CTR", "approved_plan": draft_plan},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("approved", response.json()["detail"])

    def test_jira_handoff_returns_epic_and_issue_refs(self) -> None:
        request = build_sample_request().model_dump()
        draft_plan = self.client.post("/api/v1/plans/generate", json=request).json()
        approved_plan = self.client.post("/api/v1/plans/approve", json=draft_plan).json()

        with patch(
            "contour.api.main.create_plan_epic",
            return_value={
                "key": "CTR-900",
                "url": "https://example.atlassian.net/browse/CTR-900",
                "issues": [
                    {
                        "key": "CTR-901",
                        "url": "https://example.atlassian.net/browse/CTR-901",
                        "summary": "Build planning workspace",
                        "issue_type": "Story",
                        "assignment_status": "assigned",
                        "assignee": "Avery",
                    }
                ],
            },
        ):
            response = self.client.post(
                "/api/v1/jira/handoff",
                json={"project_key": "CTR", "approved_plan": approved_plan},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "key": "CTR-900",
                "url": "https://example.atlassian.net/browse/CTR-900",
                "issues": [
                    {
                        "key": "CTR-901",
                        "url": "https://example.atlassian.net/browse/CTR-901",
                        "summary": "Build planning workspace",
                        "issue_type": "Story",
                        "assignment_status": "assigned",
                        "assignee": "Avery",
                    }
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
