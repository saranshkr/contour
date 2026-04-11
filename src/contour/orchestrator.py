from __future__ import annotations

from collections import defaultdict
import re
from typing import Iterable

from contour.jira_client import JiraClient
from contour.models import (
    CapacitySummary,
    EnrichedBacklogItem,
    MemberCapacitySummary,
    RiskFlag,
    SprintPlan,
    SprintPlanItem,
    SprintRequest,
    TeamMemberInput,
)
from contour.services.epic_handler import EpicCreationHandler
from contour.services.field_meta import FieldMetadataService
from contour.services.llm import LLMService

PRIORITY_RANK = {
    "critical": 4,
    "highest": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "lowest": 1,
}


def plan_sprint(request: SprintRequest, llm_service: LLMService | None = None) -> SprintPlan:
    llm = llm_service or LLMService()
    enriched_items = llm.enrich_backlog(request)
    proposal = llm.propose_plan(request, enriched_items)
    return _repair_plan(request, enriched_items, proposal)


def approve_plan(plan: SprintPlan) -> SprintPlan:
    return plan.model_copy(update={"approval_state": "approved"})


def create_plan_epic(
    project_key: str,
    approved_plan: SprintPlan,
    jira_client: JiraClient | None = None,
) -> str:
    if approved_plan.approval_state != "approved":
        raise ValueError("Sprint plan must be approved before Jira handoff.")

    jira = jira_client or JiraClient()
    field_service = FieldMetadataService(jira)
    handler = EpicCreationHandler(jira, field_service)

    field_requirements = field_service.get_epic_fields(project_key)
    account_id = field_service.get_user_id()
    draft_fields = _build_plan_epic_fields(approved_plan)
    mapped_fields = handler.map_fields(draft_fields, field_requirements, account_id)
    return handler.create_epic(project_key, mapped_fields)


def _repair_plan(
    request: SprintRequest,
    enriched_items: list[EnrichedBacklogItem],
    proposal: dict,
) -> SprintPlan:
    team_members = request.team_members
    item_lookup = {item.id: item for item in enriched_items}
    remaining = {member.name: member.capacity_points for member in team_members}
    assigned_points = defaultdict(int)

    selected_items: list[SprintPlanItem] = []
    deferred_items: list[EnrichedBacklogItem] = []
    deferred_ids: set[str] = set()
    selected_ids: set[str] = set()
    risks = [_coerce_risk(risk) for risk in proposal.get("risks", [])]
    explicitly_deferred = {
        item_id
        for item_id in proposal.get("deferred_ids", [])
        if item_id in item_lookup
    }

    for raw_item in proposal.get("selected_items", []):
        item_id = str(raw_item.get("id", "")).strip()
        if (
            not item_id
            or item_id in selected_ids
            or item_id not in item_lookup
            or item_id in explicitly_deferred
        ):
            continue

        item = item_lookup[item_id]
        recommended = _resolve_member_name(raw_item.get("recommended_assignee"), team_members)
        if not recommended:
            recommended = _choose_best_assignee(item, team_members, remaining)

        alternatives = _build_alternatives(item, team_members, recommended, remaining)
        selected_item = _maybe_assign_item(
            item=item,
            recommended_assignee=recommended,
            alternatives=alternatives,
            raw_item=raw_item,
            team_members=team_members,
            remaining=remaining,
            assigned_points=assigned_points,
            risks=risks,
        )
        if selected_item is None:
            deferred_items.append(item)
            deferred_ids.add(item.id)
            continue

        selected_items.append(selected_item)
        selected_ids.add(item.id)

    for item in _sorted_items(enriched_items):
        if item.id in selected_ids or item.id in deferred_ids or item.id in explicitly_deferred:
            continue
        recommended = _choose_best_assignee(item, team_members, remaining)
        alternatives = _build_alternatives(item, team_members, recommended, remaining)
        selected_item = _maybe_assign_item(
            item=item,
            recommended_assignee=recommended,
            alternatives=alternatives,
            raw_item={},
            team_members=team_members,
            remaining=remaining,
            assigned_points=assigned_points,
            risks=risks,
        )
        if selected_item is None:
            deferred_items.append(item)
            deferred_ids.add(item.id)
            continue

        selected_items.append(selected_item)
        selected_ids.add(item.id)

    for item_id in explicitly_deferred:
        if item_id not in selected_ids and item_id not in deferred_ids:
            deferred_items.append(item_lookup[item_id])
            deferred_ids.add(item_id)

    for item in _sorted_items(enriched_items):
        if item.id not in selected_ids and item.id not in deferred_ids:
            deferred_items.append(item)
            deferred_ids.add(item.id)

    _append_item_risks(selected_items, deferred_items, team_members, risks)

    capacity_summary = _build_capacity_summary(team_members, assigned_points)
    return SprintPlan(
        sprint_name=request.sprint_name,
        goal=request.goal,
        selected_items=selected_items,
        deferred_items=deferred_items,
        capacity_summary=capacity_summary,
        risks=_dedupe_risks(risks),
        approval_state="draft",
    )


def _maybe_assign_item(
    item: EnrichedBacklogItem,
    recommended_assignee: str | None,
    alternatives: list[str],
    raw_item: dict,
    team_members: list[TeamMemberInput],
    remaining: dict[str, int],
    assigned_points: defaultdict[str, int],
    risks: list[RiskFlag],
) -> SprintPlanItem | None:
    assignee = recommended_assignee or _choose_best_assignee(item, team_members, remaining)
    if not assignee:
        risks.append(
            RiskFlag(
                severity="high",
                category="skill-gap",
                message=f"No suitable assignee found for backlog item {item.id}.",
                affected_items=[item.id],
                suggested_action="Add an owner with the required skill set or defer this item.",
            )
        )
        return None

    if remaining[assignee] < item.estimated_points:
        backup_assignee = _choose_best_assignee(item, team_members, remaining, exclude={assignee})
        if backup_assignee and remaining[backup_assignee] >= item.estimated_points:
            assignee = backup_assignee
        else:
            risks.append(
                RiskFlag(
                    severity="high",
                    category="capacity",
                    message=f"{item.id} does not fit within remaining capacity for {assignee}.",
                    affected_items=[item.id],
                    suggested_action="Defer the item or increase available sprint capacity.",
                )
            )
            return None

    remaining[assignee] -= item.estimated_points
    assigned_points[assignee] += item.estimated_points

    selection_rationale = str(raw_item.get("selection_rationale") or _default_selection_rationale(item))
    assignment_rationale = str(
        raw_item.get("assignment_rationale") or _default_assignment_rationale(item, assignee, team_members)
    )

    return SprintPlanItem(
        **item.model_dump(),
        recommended_assignee=assignee,
        alternative_assignees=alternatives,
        selection_rationale=selection_rationale,
        assignment_rationale=assignment_rationale,
    )


def _choose_best_assignee(
    item: EnrichedBacklogItem,
    team_members: list[TeamMemberInput],
    remaining: dict[str, int],
    exclude: set[str] | None = None,
) -> str | None:
    exclude = exclude or set()
    ranked = sorted(
        (member for member in team_members if member.name not in exclude),
        key=lambda member: (
            _skill_overlap(item, member),
            1 if item.owner_hint and member.name.lower() == item.owner_hint.lower() else 0,
            remaining.get(member.name, 0),
        ),
        reverse=True,
    )
    for member in ranked:
        if remaining.get(member.name, 0) >= item.estimated_points:
            return member.name
    return ranked[0].name if ranked else None


def _build_alternatives(
    item: EnrichedBacklogItem,
    team_members: list[TeamMemberInput],
    recommended_assignee: str | None,
    remaining: dict[str, int],
) -> list[str]:
    ranked = sorted(
        team_members,
        key=lambda member: (_skill_overlap(item, member), remaining.get(member.name, 0)),
        reverse=True,
    )
    alternatives: list[str] = []
    for member in ranked:
        if member.name == recommended_assignee or member.name in alternatives:
            continue
        alternatives.append(member.name)
        if len(alternatives) == 2:
            break
    return alternatives


def _resolve_member_name(name: object, team_members: Iterable[TeamMemberInput]) -> str | None:
    if not isinstance(name, str):
        return None
    normalized = name.strip().lower()
    for member in team_members:
        if member.name.lower() == normalized:
            return member.name
    return None


def _skill_overlap(item: EnrichedBacklogItem, member: TeamMemberInput) -> int:
    item_skills = {_slugify(skill) for skill in item.required_skills}
    member_skills = {_slugify(skill) for skill in member.skills}
    if not item_skills:
        return 0
    return len(item_skills & member_skills)


def _append_item_risks(
    selected_items: list[SprintPlanItem],
    deferred_items: list[EnrichedBacklogItem],
    team_members: list[TeamMemberInput],
    risks: list[RiskFlag],
) -> None:
    all_team_skills = {_slugify(skill) for member in team_members for skill in member.skills}

    for item in selected_items:
        if item.ambiguity_flags:
            risks.append(
                RiskFlag(
                    severity="medium",
                    category="ambiguity",
                    message=f"{item.id} has open questions: {', '.join(item.ambiguity_flags)}.",
                    affected_items=[item.id],
                    suggested_action="Clarify acceptance criteria before starting work.",
                )
            )
        if item.dependency_signals:
            risks.append(
                RiskFlag(
                    severity="medium",
                    category="dependency",
                    message=f"{item.id} depends on {', '.join(item.dependency_signals)}.",
                    affected_items=[item.id],
                    suggested_action="Confirm the dependency is unblocked during sprint planning.",
                )
            )
        missing_skills = [_slugify(skill) for skill in item.required_skills if _slugify(skill) not in all_team_skills]
        if missing_skills:
            risks.append(
                RiskFlag(
                    severity="high",
                    category="skill-gap",
                    message=f"{item.id} requires skills the team does not clearly cover.",
                    affected_items=[item.id],
                    suggested_action="Add support from a teammate with the missing skill set or defer the item.",
                )
            )

    for item in deferred_items:
        if _priority_score(item.priority) >= PRIORITY_RANK["high"]:
            risks.append(
                RiskFlag(
                    severity="medium",
                    category="scope",
                    message=f"{item.id} is high priority but was deferred from the sprint draft.",
                    affected_items=[item.id],
                    suggested_action="Review whether lower-priority work should be swapped out.",
                )
            )


def _build_capacity_summary(
    team_members: list[TeamMemberInput],
    assigned_points: defaultdict[str, int],
) -> CapacitySummary:
    allocations = []
    total_capacity = 0
    total_selected = 0

    for member in team_members:
        assigned = assigned_points.get(member.name, 0)
        remaining = member.capacity_points - assigned
        allocations.append(
            MemberCapacitySummary(
                member_name=member.name,
                capacity_points=member.capacity_points,
                assigned_points=assigned,
                remaining_points=remaining,
            )
        )
        total_capacity += member.capacity_points
        total_selected += assigned

    return CapacitySummary(
        total_capacity_points=total_capacity,
        selected_points=total_selected,
        remaining_points=total_capacity - total_selected,
        allocations=allocations,
    )


def _build_plan_epic_fields(plan: SprintPlan) -> dict[str, object]:
    selected_lines = [
        f"- {item.id}: {item.title} ({item.estimated_points} pts) -> {item.recommended_assignee}"
        for item in plan.selected_items
    ]
    deferred_lines = [
        f"- {item.id}: {item.title} ({item.estimated_points} pts)"
        for item in plan.deferred_items
    ] or ["- None"]
    risk_lines = [f"- [{risk.severity.upper()}] {risk.message}" for risk in plan.risks] or ["- No major risks flagged."]
    capacity_lines = [
        f"- {allocation.member_name}: {allocation.assigned_points}/{allocation.capacity_points} pts"
        for allocation in plan.capacity_summary.allocations
    ]
    labels = _build_labels(plan)

    description = "\n".join(
        [
            f"Sprint goal: {plan.goal}",
            "",
            "Selected sprint items:",
            *(selected_lines or ["- None selected"]),
            "",
            "Deferred items:",
            *deferred_lines,
            "",
            "Capacity summary:",
            *capacity_lines,
            "",
            "Planning risks:",
            *risk_lines,
        ]
    )

    return {
        "summary": f"{plan.sprint_name}: {plan.goal}",
        "Epic Name": plan.sprint_name,
        "description": description,
        "priority": _epic_priority(plan),
        "labels": labels,
    }


def _build_labels(plan: SprintPlan) -> list[str]:
    labels = {"contour"}
    sprint_label = _slugify(plan.sprint_name)
    if sprint_label:
        labels.add(sprint_label)
    for item in plan.selected_items:
        for label in item.labels:
            if label:
                labels.add(_slugify(label))
    return sorted(label for label in labels if label)


def _epic_priority(plan: SprintPlan) -> str:
    if any(risk.severity == "high" for risk in plan.risks):
        return "High"
    if any(_priority_score(item.priority) >= PRIORITY_RANK["high"] for item in plan.selected_items):
        return "High"
    return "Medium"


def _coerce_risk(risk: object) -> RiskFlag:
    if isinstance(risk, RiskFlag):
        return risk
    return RiskFlag.model_validate(risk)


def _dedupe_risks(risks: list[RiskFlag]) -> list[RiskFlag]:
    deduped: list[RiskFlag] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for risk in risks:
        key = (risk.category, risk.message, tuple(risk.affected_items))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped


def _default_selection_rationale(item: EnrichedBacklogItem) -> str:
    return (
        f"Selected because {item.id} is {item.priority.lower()} priority, "
        f"fits within the sprint at {item.estimated_points} points, and supports the sprint goal."
    )


def _default_assignment_rationale(
    item: EnrichedBacklogItem,
    assignee: str,
    team_members: list[TeamMemberInput],
) -> str:
    team_member = next((member for member in team_members if member.name == assignee), None)
    if not team_member:
        return f"Assigned to {assignee} based on remaining capacity."
    matching_skills = [
        skill for skill in team_member.skills if _slugify(skill) in {_slugify(req) for req in item.required_skills}
    ]
    if matching_skills:
        return f"Assigned to {assignee} because their skills match {', '.join(matching_skills)}."
    return f"Assigned to {assignee} based on available capacity and role fit."


def _sorted_items(items: list[EnrichedBacklogItem]) -> list[EnrichedBacklogItem]:
    return sorted(
        items,
        key=lambda item: (_priority_score(item.priority), item.analysis_confidence, -item.estimated_points),
        reverse=True,
    )


def _priority_score(priority: str) -> int:
    return PRIORITY_RANK.get(priority.strip().lower(), PRIORITY_RANK["medium"])


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
