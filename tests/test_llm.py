from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contour.models import EmployeeRecord, SprintRequest
from contour.services.llm import LLMService, _is_gpt5_family_model


class LLMServiceTests(unittest.TestCase):
    def test_gpt5_family_detection(self) -> None:
        self.assertTrue(_is_gpt5_family_model("gpt-5.4-mini"))
        self.assertTrue(_is_gpt5_family_model("gpt-5-mini"))
        self.assertFalse(_is_gpt5_family_model("gpt-4o"))

    def test_gpt5_defaults_to_low_reasoning_effort(self) -> None:
        service = LLMService(model_name="gpt-5.4-mini", prefer_llm=False)
        self.assertEqual(service.reasoning_effort, "low")

    def test_non_gpt5_keeps_reasoning_effort_unset_by_default(self) -> None:
        service = LLMService(model_name="gpt-4o", prefer_llm=False)
        self.assertIsNone(service.reasoning_effort)

    def test_parse_json_payload_accepts_fenced_json(self) -> None:
        payload = LLMService._parse_json_payload(
            "```json\n{\"items\": []}\n```"
        )
        self.assertEqual(payload, {"items": []})

    def test_build_responses_request_options_avoids_temperature(self) -> None:
        service = LLMService(model_name="gpt-5.4-mini", prefer_llm=False)
        options = service._build_responses_request_options("Normalize the tasks")

        self.assertEqual(options["model"], "gpt-5.4-mini")
        self.assertEqual(options["input"], "Normalize the tasks")
        self.assertEqual(options["reasoning"], {"effort": "low"})
        self.assertNotIn("temperature", options)

    def test_normalization_prompt_requires_story_points_and_issue_type(self) -> None:
        service = LLMService(prefer_llm=False)
        request = SprintRequest(
            sprint_name="Sprint 18",
            goal="Ship the Contour MVP flow",
            tasks=[
                {
                    "text": "Build the planning workspace for the Contour web app.",
                    "owner_hint": "Avery",
                }
            ],
        )
        employees = [
            EmployeeRecord(
                id="emp-avery",
                name="Avery",
                role="Engineer",
                skills=["frontend"],
                capacity_points=5,
                jira_account_id="acct-avery",
            )
        ]

        prompt = service._build_normalization_prompt(request, employees)

        self.assertIn("jira_issue_type", prompt)
        self.assertIn("story_points must be one of 1, 2, 3, 5, 8", prompt)
        self.assertIn("Estimate story_points using priority, implementation complexity, and the skills required", prompt)
        self.assertIn("employees", prompt)


if __name__ == "__main__":
    unittest.main()
