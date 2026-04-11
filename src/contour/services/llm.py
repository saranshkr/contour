from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from contour.models import EnrichedBacklogItem, RiskFlag, SprintRequest, TeamMemberInput

try:
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - optional runtime dependency
    JsonOutputParser = None
    ChatPromptTemplate = None
    ChatOpenAI = None


class _EnrichmentBatch(BaseModel):
    items: list[EnrichedBacklogItem]


class _PlanProposalItem(BaseModel):
    id: str
    recommended_assignee: str
    alternative_assignees: list[str] = Field(default_factory=list)
    selection_rationale: str
    assignment_rationale: str


class _PlanProposal(BaseModel):
    selected_items: list[_PlanProposalItem] = Field(default_factory=list)
    deferred_ids: list[str] = Field(default_factory=list)
    risks: list[RiskFlag] = Field(default_factory=list)


class LLMService:
    """LLM-backed planning service with a deterministic fallback."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.2,
        prefer_llm: bool = True,
    ):
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.temperature = temperature
        self.prefer_llm = prefer_llm
        self._enrichment_chain = None
        self._plan_chain = None

        if (
            prefer_llm
            and ChatOpenAI is not None
            and ChatPromptTemplate is not None
            and JsonOutputParser is not None
            and os.getenv("OPENAI_API_KEY")
        ):
            self._build_chains()

    def enrich_backlog(self, request: SprintRequest) -> list[EnrichedBacklogItem]:
        if self._enrichment_chain is not None:
            try:
                result = self._enrichment_chain.invoke(
                    {"prompt": self._build_enrichment_prompt(request)}
                )
                batch = _EnrichmentBatch.model_validate(result)
                if len(batch.items) == len(request.backlog_items):
                    return batch.items
            except Exception:
                pass
        return self._fallback_enrichment(request)

    def propose_plan(
        self,
        request: SprintRequest,
        enriched_items: list[EnrichedBacklogItem],
    ) -> dict[str, Any]:
        if self._plan_chain is not None:
            try:
                result = self._plan_chain.invoke(
                    {"prompt": self._build_plan_prompt(request, enriched_items)}
                )
                proposal = _PlanProposal.model_validate(result)
                return proposal.model_dump()
            except Exception:
                pass
        return self._fallback_plan(request, enriched_items)

    def _build_chains(self) -> None:
        llm = ChatOpenAI(model_name=self.model_name, temperature=self.temperature)

        enrichment_parser = JsonOutputParser(pydantic_object=_EnrichmentBatch)
        enrichment_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are Contour, an expert sprint planning copilot. "
                    "Normalize backlog items for planning and return JSON only.",
                ),
                ("user", "{prompt}"),
            ]
        )
        self._enrichment_chain = enrichment_prompt | llm | enrichment_parser

        plan_parser = JsonOutputParser(pydantic_object=_PlanProposal)
        plan_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are Contour, an expert engineering planning copilot. "
                    "Recommend sprint scope, ownership, and risks. Return JSON only.",
                ),
                ("user", "{prompt}"),
            ]
        )
        self._plan_chain = plan_prompt | llm | plan_parser

    def _build_enrichment_prompt(self, request: SprintRequest) -> str:
        payload = {
            "sprint_name": request.sprint_name,
            "goal": request.goal,
            "backlog_items": [item.model_dump() for item in request.backlog_items],
            "team_members": [member.model_dump() for member in request.team_members],
        }
        return "\n".join(
            [
                "Enrich each backlog item for sprint planning.",
                "Infer estimated_points using story point buckets 1, 2, 3, 5, or 8.",
                "Infer required_skills based on the backlog content and team context.",
                "Flag ambiguity when the work is vague or underspecified.",
                "Return an items array with one enriched record per input backlog item.",
                json.dumps(payload, indent=2),
            ]
        )

    def _build_plan_prompt(
        self,
        request: SprintRequest,
        enriched_items: list[EnrichedBacklogItem],
    ) -> str:
        payload = {
            "sprint_name": request.sprint_name,
            "goal": request.goal,
            "enriched_items": [item.model_dump() for item in enriched_items],
            "team_members": [member.model_dump() for member in request.team_members],
        }
        return "\n".join(
            [
                "Create a draft sprint plan.",
                "Choose the sprint items that best fit the goal and team capacity.",
                "Recommend one primary assignee and up to two alternatives for each selected item.",
                "Return selected_items, deferred_ids, and risks.",
                json.dumps(payload, indent=2),
            ]
        )

    def _fallback_enrichment(self, request: SprintRequest) -> list[EnrichedBacklogItem]:
        all_team_skills = [skill for member in request.team_members for skill in member.skills]
        enriched: list[EnrichedBacklogItem] = []
        for item in request.backlog_items:
            required_skills = self._infer_required_skills(item.title, item.description, item.labels, all_team_skills)
            ambiguity_flags = self._infer_ambiguity_flags(item.description)
            dependency_signals = list(item.dependencies)
            if "depends on" in item.description.lower():
                dependency_signals.append("dependency noted in description")

            confidence = 0.95
            confidence -= 0.15 * len(ambiguity_flags)
            confidence -= 0.1 * len(dependency_signals)

            enriched.append(
                EnrichedBacklogItem(
                    **item.model_dump(),
                    estimated_points=self._estimate_points(item.title, item.description, item.dependencies),
                    required_skills=required_skills,
                    ambiguity_flags=ambiguity_flags,
                    dependency_signals=dependency_signals,
                    analysis_confidence=max(0.3, round(confidence, 2)),
                )
            )
        return enriched

    def _fallback_plan(
        self,
        request: SprintRequest,
        enriched_items: list[EnrichedBacklogItem],
    ) -> dict[str, Any]:
        remaining_total = sum(member.capacity_points for member in request.team_members)
        selected_items = []
        deferred_ids = []
        risks: list[RiskFlag] = []

        for item in sorted(
            enriched_items,
            key=lambda enriched: (
                self._priority_score(enriched.priority),
                enriched.analysis_confidence,
                -enriched.estimated_points,
            ),
            reverse=True,
        ):
            if item.estimated_points > remaining_total:
                deferred_ids.append(item.id)
                continue

            assignee, alternatives = self._rank_assignees(item, request.team_members)
            selected_items.append(
                {
                    "id": item.id,
                    "recommended_assignee": assignee,
                    "alternative_assignees": alternatives,
                    "selection_rationale": (
                        f"Included because {item.id} aligns to the sprint goal and fits within the "
                        f"overall sprint budget at {item.estimated_points} points."
                    ),
                    "assignment_rationale": (
                        f"Assigned to {assignee} based on the best apparent skill match and available capacity."
                    ),
                }
            )
            remaining_total -= item.estimated_points

            if item.ambiguity_flags:
                risks.append(
                    RiskFlag(
                        severity="medium",
                        category="ambiguity",
                        message=f"{item.id} may need clarification before development starts.",
                        affected_items=[item.id],
                        suggested_action="Review the ticket details and tighten the acceptance criteria.",
                    )
                )

        for item in enriched_items:
            if item.id not in {selected["id"] for selected in selected_items} and item.id not in deferred_ids:
                deferred_ids.append(item.id)

        return {
            "selected_items": selected_items,
            "deferred_ids": deferred_ids,
            "risks": [risk.model_dump() for risk in risks],
        }

    def _estimate_points(self, title: str, description: str, dependencies: list[str]) -> int:
        text = f"{title} {description}".lower()
        complexity_score = 1
        complexity_score += min(len(dependencies), 2)
        complexity_score += len(re.findall(r"\b(api|integration|workflow|approval|analytics|auth|migration)\b", text))
        if len(description.split()) > 20:
            complexity_score += 1
        if len(description.split()) > 40:
            complexity_score += 1

        if complexity_score <= 1:
            return 1
        if complexity_score == 2:
            return 2
        if complexity_score == 3:
            return 3
        if complexity_score == 4:
            return 5
        return 8

    def _infer_required_skills(
        self,
        title: str,
        description: str,
        labels: list[str],
        team_skills: list[str],
    ) -> list[str]:
        combined_text = " ".join([title, description, " ".join(labels)]).lower()
        normalized_skill_map = {self._normalize(skill): skill for skill in team_skills}
        matches = []
        for normalized_skill, original in normalized_skill_map.items():
            token = normalized_skill.replace("-", " ")
            if token in combined_text or normalized_skill in self._normalize(combined_text):
                matches.append(original)

        if matches:
            return sorted(set(matches))

        heuristics = {
            "frontend": ["ui", "streamlit", "frontend"],
            "backend": ["api", "service", "pipeline", "backend"],
            "jira": ["jira", "atlassian"],
            "integration": ["integration", "sync", "handoff"],
            "ai": ["llm", "ai", "prompt"],
            "python": ["python"],
        }
        inferred = [
            skill
            for skill, keywords in heuristics.items()
            if any(keyword in combined_text for keyword in keywords)
        ]
        return inferred

    def _infer_ambiguity_flags(self, description: str) -> list[str]:
        lowered = description.lower()
        flags = []
        if len(description.split()) < 8:
            flags.append("description is brief")
        if any(token in lowered for token in ("tbd", "todo", "etc", "somehow", "improve")):
            flags.append("scope is underspecified")
        if "?" in description:
            flags.append("open questions remain")
        return flags

    def _rank_assignees(
        self,
        item: EnrichedBacklogItem,
        team_members: list[TeamMemberInput],
    ) -> tuple[str, list[str]]:
        scored = sorted(
            team_members,
            key=lambda member: (
                self._assignee_score(item, member),
                member.capacity_points,
            ),
            reverse=True,
        )
        if not scored:
            return "Unassigned", []
        primary = scored[0].name
        alternatives = [member.name for member in scored[1:3]]
        return primary, alternatives

    def _assignee_score(self, item: EnrichedBacklogItem, member: TeamMemberInput) -> tuple[int, int]:
        required = Counter(self._normalize(skill) for skill in item.required_skills)
        available = Counter(self._normalize(skill) for skill in member.skills)
        overlap = sum((required & available).values())
        owner_hint_bonus = 1 if item.owner_hint and member.name.lower() == item.owner_hint.lower() else 0
        return overlap, owner_hint_bonus

    def _priority_score(self, priority: str) -> int:
        order = {"critical": 4, "highest": 4, "high": 3, "medium": 2, "low": 1, "lowest": 1}
        return order.get(priority.strip().lower(), 2)

    def _normalize(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
