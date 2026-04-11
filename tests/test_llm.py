from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
            "```json\n{\"selected_items\": [], \"deferred_ids\": [], \"risks\": []}\n```"
        )
        self.assertEqual(
            payload,
            {"selected_items": [], "deferred_ids": [], "risks": []},
        )

    def test_build_responses_request_options_avoids_temperature(self) -> None:
        service = LLMService(model_name="gpt-5.4-mini", prefer_llm=False)
        options = service._build_responses_request_options("Plan the sprint")

        self.assertEqual(options["model"], "gpt-5.4-mini")
        self.assertEqual(options["input"], "Plan the sprint")
        self.assertEqual(options["reasoning"], {"effort": "low"})
        self.assertNotIn("temperature", options)


if __name__ == "__main__":
    unittest.main()
