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

    def test_generate_plan_returns_draft_plan_with_validation(self) -> None:
        request = build_sample_request().model_dump(by_alias=True)

        response = self.client.post("/api/v1/plans/generate", json=request)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["approval_state"], "draft")
        self.assertIn("capacity_summary", payload)
        self.assertIn("plan_items", payload)
        self.assertIn("validation_result", payload)

    def test_jira_dry_run_returns_payload_preview(self) -> None:
        request = build_sample_request().model_dump(by_alias=True)
        draft_plan = self.client.post("/api/v1/plans/generate", json=request).json()

        with patch(
            "contour.api.main.dry_run_plan_handoff",
            return_value={
                "idempotency_key": "CTR-abc123",
                "epic_payload_preview": {"issue_type": "Epic", "fields": {"summary": "Sprint 18"}},
                "child_issue_payload_previews": [
                    {"issue_type": "Story", "fields": {"summary": "Build planning workspace"}, "task_id": "TASK-1"}
                ],
                "validation_errors": [],
                "validation_warnings": [],
                "estimated_jira_objects": 2,
                "safe_to_execute": True,
                "sync_state": {
                    "idempotency_key": "CTR-abc123",
                    "project_key": "CTR",
                    "status": "DRY_RUN_PASSED",
                    "epic_key": None,
                    "child_issue_keys": {},
                    "validation_errors": [],
                    "validation_warnings": [],
                    "last_error": None,
                },
            },
        ) as dry_run_mock:
            response = self.client.post(
                "/api/v1/jira/dry-run",
                json={"project_key": "CTR", "approved_plan": draft_plan, "accept_warnings": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["safe_to_execute"])
        self.assertEqual(response.json()["estimated_jira_objects"], 2)
        self.assertTrue(dry_run_mock.call_args.kwargs["accept_warnings"])
        self.assertGreaterEqual(len(dry_run_mock.call_args.kwargs["engineers"]), 1)

    def test_jira_handoff_requires_approval(self) -> None:
        request = build_sample_request().model_dump(by_alias=True)
        draft_plan = self.client.post("/api/v1/plans/generate", json=request).json()

        response = self.client.post(
            "/api/v1/jira/handoff",
            json={"project_key": "CTR", "approved_plan": draft_plan},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("approved", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
