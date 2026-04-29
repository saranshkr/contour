from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from contour.models import (
    BacklogItem,
    EmployeeRecord,
    NormalizedTask,
    SprintRequest,
    STORY_POINT_BUCKETS,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional runtime dependency
    OpenAI = None

try:
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - optional runtime dependency
    JsonOutputParser = None
    ChatPromptTemplate = None
    ChatOpenAI = None


class _NormalizedTaskBatch(BaseModel):
    items: list[NormalizedTask]


def _is_gpt5_family_model(model_name: str) -> bool:
    normalized = model_name.strip().lower()
    return normalized.startswith("gpt-5")


class LLMService:
    """LLM-backed task normalization with a deterministic fallback."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.2,
        prefer_llm: bool = True,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
    ):
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        self.temperature = temperature
        self.prefer_llm = prefer_llm
        self.reasoning_effort = reasoning_effort
        self.text_verbosity = text_verbosity
        if _is_gpt5_family_model(self.model_name):
            self.reasoning_effort = self.reasoning_effort or os.getenv("OPENAI_REASONING_EFFORT") or "low"
            self.text_verbosity = self.text_verbosity or os.getenv("OPENAI_TEXT_VERBOSITY")
        self._normalization_chain = None
        self._responses_client = None

        if prefer_llm and os.getenv("OPENAI_API_KEY"):
            if _is_gpt5_family_model(self.model_name) and OpenAI is not None:
                self._responses_client = OpenAI()
            elif (
                ChatOpenAI is not None
                and ChatPromptTemplate is not None
                and JsonOutputParser is not None
            ):
                self._build_chain()

    def normalize_tasks(
        self,
        request: SprintRequest,
        employees: list[EmployeeRecord],
    ) -> list[NormalizedTask]:
        if self._responses_client is not None:
            try:
                result = self._invoke_responses_json(
                    self._build_normalization_prompt(request, employees)
                )
                batch = _NormalizedTaskBatch.model_validate(result)
                if len(batch.items) == len(request.tasks):
                    return batch.items
            except Exception:
                pass
        if self._normalization_chain is not None:
            try:
                result = self._normalization_chain.invoke(
                    {"prompt": self._build_normalization_prompt(request, employees)}
                )
                batch = _NormalizedTaskBatch.model_validate(result)
                if len(batch.items) == len(request.tasks):
                    return batch.items
            except Exception:
                pass
        return self._fallback_normalization(request, employees)

    def _build_chain(self) -> None:
        llm = ChatOpenAI(model_name=self.model_name, temperature=self.temperature)
        parser = JsonOutputParser(pydantic_object=_NormalizedTaskBatch)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are Contour, an expert engineering planning copilot. "
                    "Normalize natural-language tasks into Jira-ready planning records and return JSON only.",
                ),
                ("user", "{prompt}"),
            ]
        )
        self._normalization_chain = prompt | llm | parser

    def _invoke_responses_json(self, prompt: str) -> dict[str, Any]:
        if self._responses_client is None:
            raise RuntimeError("OpenAI Responses client is not configured")

        response = self._responses_client.responses.create(
            **self._build_responses_request_options(prompt)
        )
        return self._parse_json_payload(self._extract_output_text(response))

    def _build_responses_request_options(self, prompt: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "model": self.model_name,
            "input": prompt,
        }
        if self.reasoning_effort:
            options["reasoning"] = {"effort": self.reasoning_effort}
        if self.text_verbosity:
            options["text"] = {"verbosity": self.text_verbosity}
        return options

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        fragments: list[str] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) not in {"output_text", "text"}:
                    continue
                text = getattr(content, "text", "")
                if text:
                    fragments.append(text)
        return "\n".join(fragments)

    @staticmethod
    def _parse_json_payload(raw_text: str) -> dict[str, Any]:
        cleaned = raw_text.strip()
        fenced_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fenced_match:
            cleaned = fenced_match.group(1).strip()

        candidates = [cleaned]
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            candidates.append(cleaned[json_start : json_end + 1])

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

        raise ValueError("Model response did not contain a valid JSON object")

    def _build_normalization_prompt(
        self,
        request: SprintRequest,
        employees: list[EmployeeRecord],
    ) -> str:
        payload = {
            "sprint_name": request.sprint_name,
            "goal": request.goal,
            "tasks": [task.model_dump() for task in request.tasks],
            "employees": [employee.model_dump(exclude={"jira_account_id"}) for employee in employees],
        }
        return "\n".join(
            [
                "Normalize each natural-language task into a Jira-ready planning record.",
                "Return JSON only with one output item per input task.",
                "For each item, include task_id, source_index, task_text, owner_hint, title, description, priority, jira_issue_type, story_points, required_skills, and estimation_rationale.",
                "Priority must be one of low, medium, or high.",
                "jira_issue_type must be either Story or Task.",
                f"story_points must be one of {', '.join(str(bucket) for bucket in STORY_POINT_BUCKETS)}.",
                "Estimate story_points using priority, implementation complexity, and the skills required for the work.",
                "Infer required_skills using only the task text and the provided employee roster.",
                "Use Story for product-facing or user-visible work and Task for platform, integration, operational, or internal work.",
                "Write concise Jira-style titles and actionable descriptions.",
                json.dumps(payload, indent=2),
            ]
        )

    def _fallback_normalization(
        self,
        request: SprintRequest,
        employees: list[EmployeeRecord],
    ) -> list[NormalizedTask]:
        all_skills = [skill for employee in employees for skill in employee.skills]
        return [
            self._normalize_task(index, task, all_skills)
            for index, task in enumerate(request.tasks)
        ]

    def _normalize_task(
        self,
        index: int,
        task: BacklogItem,
        all_skills: list[str],
    ) -> NormalizedTask:
        task_text = task.text or " ".join(part for part in [task.title, task.description] if part)
        if not task_text:
            task_text = f"Backlog item {index + 1}"
        return NormalizedTask(
            task_id=f"TASK-{index + 1}",
            source_index=index,
            task_text=task_text,
            owner_hint=task.owner_hint,
            backlog_item_id=task.id,
            title=task.title or self._infer_title(task_text),
            description=task.description or self._infer_description(task_text),
            acceptance_criteria=task.acceptance_criteria,
            priority=self._infer_priority(task_text),
            jira_issue_type=self._infer_issue_type(task_text),
            story_points=self._estimate_story_points(task_text, all_skills),
            required_skills=self._infer_required_skills(task_text, all_skills),
            estimation_rationale=self._build_estimation_rationale(task_text),
        )

    def _infer_title(self, task_text: str) -> str:
        clipped = task_text.strip().split(".")[0]
        words = clipped.split()
        if len(words) <= 8:
            return clipped.rstrip(".")
        return " ".join(words[:8]).rstrip(".")

    def _infer_description(self, task_text: str) -> str:
        text = task_text.strip()
        return text if text.endswith(".") else f"{text}."

    def _infer_priority(self, task_text: str) -> str:
        text = task_text.lower()
        if any(token in text for token in ("urgent", "critical", "immediately", "blocker", "must")):
            return "high"
        if any(token in text for token in ("nice to have", "later", "follow-up", "polish")):
            return "low"
        return "medium"

    def _infer_issue_type(self, task_text: str) -> str:
        text = task_text.lower()
        if any(
            token in text
            for token in ("integration", "infra", "migration", "automation", "pipeline", "backend", "api")
        ):
            return "Task"
        return "Story"

    def _infer_required_skills(self, task_text: str, employee_skills: list[str]) -> list[str]:
        normalized_text = self._normalize(task_text)
        normalized_skill_map = {self._normalize(skill): skill for skill in employee_skills}
        matches: list[str] = []
        for normalized_skill, original in normalized_skill_map.items():
            token = normalized_skill.replace("-", " ")
            if token in task_text.lower() or normalized_skill in normalized_text:
                matches.append(original)

        if matches:
            return sorted({skill for skill in matches})

        heuristics = {
            "frontend": ["ui", "frontend", "react", "web", "page"],
            "backend": ["backend", "api", "service"],
            "jira": ["jira", "atlassian"],
            "integration": ["integration", "sync", "handoff"],
            "ai": ["ai", "llm", "model"],
            "python": ["python", "fastapi"],
            "automation": ["automation", "workflow", "pipeline"],
        }
        inferred = [
            skill
            for skill, keywords in heuristics.items()
            if any(keyword in task_text.lower() for keyword in keywords)
        ]
        return inferred

    def _estimate_story_points(self, task_text: str, employee_skills: list[str]) -> int:
        text = task_text.lower()
        priority = self._infer_priority(task_text)
        required_skills = self._infer_required_skills(task_text, employee_skills)

        score = 1
        score += 2 if priority == "high" else 1 if priority == "medium" else 0
        score += min(len(required_skills), 2)
        score += len(
            re.findall(
                r"\b(api|integration|workflow|migration|analytics|auth|dashboard|approval|jira)\b",
                text,
            )
        )
        if len(task_text.split()) > 18:
            score += 1
        if len(task_text.split()) > 35:
            score += 1

        if score <= 2:
            return 1
        if score == 3:
            return 2
        if score == 4:
            return 3
        if score in (5, 6):
            return 5
        return 8

    def _build_estimation_rationale(self, task_text: str) -> str:
        priority = self._infer_priority(task_text)
        issue_type = self._infer_issue_type(task_text)
        return (
            f"Estimated from {priority} priority work, the likely implementation complexity, "
            f"and the depth of coordination implied by this {issue_type.lower()}."
        )

    def _normalize(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
