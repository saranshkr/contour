from __future__ import annotations

from collections import defaultdict
import re

from contour.jira_client import JiraClient
from contour.models import (
    AssignmentStatus,
    CapacitySummary,
    EmployeeRecord,
    JiraHandoffResult,
    JiraIssueResult,
    MemberCapacitySummary,
    NormalizedTask,
    PlanItem,
    PriorityLevel,
    RiskFlag,
    SprintPlan,
    SprintRequest,
)
from contour.sample_data import build_employee_roster
from contour.services.epic_handler import EpicCreationHandler
from contour.services.field_meta import FieldMetadataService
from contour.services.llm import LLMService

PRIORITY_RANK: dict[PriorityLevel, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}

ASSIGNED_STATUSES = {"assigned", "assigned_with_skill_gap"}
UNASSIGNED_STATUSES = {"unassigned_capacity", "unassigned_skill_gap"}


def plan_sprint(request: SprintRequest, llm_service: LLMService | None = None) -> SprintPlan:
    employees = build_employee_roster()
    llm = llm_service or LLMService()
    normalized_items = _repair_normalized_tasks(
        request=request,
        employees=employees,
        normalized_items=llm.normalize_tasks(request, employees),
    )
    return _build_plan(
        sprint_name=request.sprint_name,
        goal=request.goal,
        normalized_items=normalized_items,
        employees=employees,
        approval_state="draft",
    )


def approve_plan(plan: SprintPlan) -> SprintPlan:
    employees = build_employee_roster()
    normalized_items = [_normalized_from_plan_item(item) for item in plan.plan_items]
    plan_by_task_id = {item.task_id: item for item in plan.plan_items}
    repaired = _build_plan(
        sprint_name=plan.sprint_name,
        goal=plan.goal,
        normalized_items=normalized_items,
        employees=employees,
        manual_items=plan_by_task_id,
        approval_state="approved",
    )
    return repaired


def create_plan_epic(
    project_key: str,
    approved_plan: SprintPlan,
    jira_client: JiraClient | None = None,
) -> JiraHandoffResult:
    if approved_plan.approval_state != "approved":
        raise ValueError("Sprint plan must be approved before Jira handoff.")

    jira = jira_client or JiraClient()
    field_service = FieldMetadataService(jira)
    handler = EpicCreationHandler(jira, field_service)

    field_requirements = field_service.get_epic_fields(project_key)
    account_id = field_service.get_user_id()
    draft_fields = _build_plan_epic_fields(approved_plan)
    mapped_fields = handler.map_fields(draft_fields, field_requirements, account_id)
    epic_key = handler.create_epic(project_key, mapped_fields)
    epic_url = _issue_url(jira.base_url, epic_key)

    issues: list[JiraIssueResult] = []
    for item in approved_plan.plan_items:
        issue_fields = field_service.get_issue_type_fields(project_key, item.jira_issue_type)
        child_draft = _build_child_issue_fields(
            item=item,
            epic_key=epic_key,
            field_requirements=issue_fields,
            field_service=field_service,
        )
        mapped_child = handler.map_fields(child_draft, issue_fields, account_id)
        if item.assignment_status in ASSIGNED_STATUSES and item.recommended_assignee_account_id:
            mapped_child["assignee"] = {"id": item.recommended_assignee_account_id}
        child_key = handler.create_issue(project_key, item.jira_issue_type, mapped_child)
        issues.append(
            JiraIssueResult(
                key=child_key,
                url=_issue_url(jira.base_url, child_key),
                summary=item.title,
                issue_type=item.jira_issue_type,
                assignment_status=item.assignment_status,
                assignee=item.recommended_assignee,
            )
        )

    return JiraHandoffResult(key=epic_key, url=epic_url, issues=issues)


def _build_plan(
    sprint_name: str,
    goal: str,
    normalized_items: list[NormalizedTask],
    employees: list[EmployeeRecord],
    manual_items: dict[str, PlanItem] | None = None,
    approval_state: str = "draft",
) -> SprintPlan:
    manual_items = manual_items or {}
    remaining = {employee.id: employee.capacity_points for employee in employees}
    assigned_points: defaultdict[str, int] = defaultdict(int)
    built_items: list[PlanItem] = []

    for item in _sorted_items(normalized_items):
        plan_item = _plan_item_from_task(
            item=item,
            employees=employees,
            remaining=remaining,
            assigned_points=assigned_points,
            manual_item=manual_items.get(item.task_id),
        )
        built_items.append(plan_item)

    capacity_summary = _build_capacity_summary(employees, assigned_points, built_items)
    risks = _collect_plan_risks(built_items, capacity_summary)
    return SprintPlan(
        sprint_name=sprint_name,
        goal=goal,
        plan_items=built_items,
        capacity_summary=capacity_summary,
        risks=risks,
        approval_state=approval_state,
    )


def _repair_normalized_tasks(
    request: SprintRequest,
    employees: list[EmployeeRecord],
    normalized_items: list[NormalizedTask],
) -> list[NormalizedTask]:
    employee_skills = [skill for employee in employees for skill in employee.skills]
    repaired: list[NormalizedTask] = []
    for index, task in enumerate(request.tasks):
        if index < len(normalized_items):
            item = normalized_items[index]
            raw = item.model_dump()
        else:
            raw = {}

        required_skills = raw.get("required_skills") or _infer_required_skills(task.text, employee_skills)
        story_points = raw.get("story_points")
        if story_points not in {1, 2, 3, 5, 8}:
            story_points = _estimate_story_points(task.text, required_skills)

        repaired.append(
            NormalizedTask(
                task_id=f"TASK-{index + 1}",
                source_index=index,
                task_text=task.text,
                owner_hint=task.owner_hint,
                title=raw.get("title") or _infer_title(task.text),
                description=raw.get("description") or _infer_description(task.text),
                priority=_normalize_priority(raw.get("priority")),
                jira_issue_type=_normalize_issue_type(raw.get("jira_issue_type")),
                story_points=story_points,
                required_skills=required_skills,
                estimation_rationale=raw.get("estimation_rationale")
                or _fallback_estimation_rationale(task.text),
            )
        )
    return repaired


def _normalized_from_plan_item(item: PlanItem) -> NormalizedTask:
    return NormalizedTask(
        task_id=item.task_id,
        source_index=item.source_index,
        task_text=item.task_text,
        owner_hint=item.owner_hint,
        title=item.title,
        description=item.description,
        priority=item.priority,
        jira_issue_type=item.jira_issue_type,
        story_points=item.story_points,
        required_skills=item.required_skills,
        estimation_rationale=item.estimation_rationale,
    )


def _plan_item_from_task(
    item: NormalizedTask,
    employees: list[EmployeeRecord],
    remaining: dict[str, int],
    assigned_points: defaultdict[str, int],
    manual_item: PlanItem | None = None,
) -> PlanItem:
    explicit_unassigned = manual_item is not None and (
        manual_item.recommended_assignee is None
        and manual_item.recommended_assignee_account_id is None
        and manual_item.assignment_status in UNASSIGNED_STATUSES
    )

    if explicit_unassigned:
        assignment_status = manual_item.assignment_status
        employee = None
    else:
        preferred_employee = _resolve_manual_employee(manual_item, employees)
        assignment_status, employee = _choose_assignment(
            item=item,
            employees=employees,
            remaining=remaining,
            preferred_employee=preferred_employee,
        )

    if employee is not None:
        remaining[employee.id] -= item.story_points
        assigned_points[employee.id] += item.story_points

    alternatives = _build_alternatives(item, employees, remaining, employee)
    risk_flags = _risk_flags_for_item(item, assignment_status)
    recommended_assignee = employee.name if employee is not None else None
    recommended_account_id = employee.jira_account_id if employee is not None else None

    selection_rationale = (
        manual_item.selection_rationale
        if manual_item is not None
        else _default_selection_rationale(item)
    )
    assignment_rationale = _assignment_rationale(
        item=item,
        assignment_status=assignment_status,
        employee=employee,
        manual_item=manual_item,
    )

    return PlanItem(
        **item.model_dump(),
        recommended_assignee=recommended_assignee,
        recommended_assignee_account_id=recommended_account_id,
        alternative_assignees=alternatives,
        assignment_status=assignment_status,
        selection_rationale=selection_rationale,
        assignment_rationale=assignment_rationale,
        risk_flags=risk_flags,
    )


def _choose_assignment(
    item: NormalizedTask,
    employees: list[EmployeeRecord],
    remaining: dict[str, int],
    preferred_employee: EmployeeRecord | None = None,
) -> tuple[AssignmentStatus, EmployeeRecord | None]:
    ranked = _rank_employees(item, employees, remaining)
    if not ranked:
        return "unassigned_capacity", None

    if preferred_employee is not None:
        manual_status = _assignment_status_for_employee(item, preferred_employee, remaining)
        if manual_status in ASSIGNED_STATUSES:
            return manual_status, preferred_employee
        return manual_status, None

    matching_ranked = [
        employee for employee in ranked if _skill_overlap(item, employee) > 0 or not item.required_skills
    ]
    if not matching_ranked and item.required_skills:
        if item.priority == "high":
            candidate = next(
                (employee for employee in ranked if remaining[employee.id] >= item.story_points),
                None,
            )
            if candidate is None:
                return "unassigned_capacity", None
            return "assigned_with_skill_gap", candidate
        return "unassigned_skill_gap", None

    candidate = next(
        (employee for employee in matching_ranked if remaining[employee.id] >= item.story_points),
        None,
    )
    if candidate is None:
        return "unassigned_capacity", None
    return "assigned", candidate


def _assignment_status_for_employee(
    item: NormalizedTask,
    employee: EmployeeRecord,
    remaining: dict[str, int],
) -> AssignmentStatus:
    if remaining.get(employee.id, 0) < item.story_points:
        return "unassigned_capacity"
    if _skill_overlap(item, employee) == 0 and item.required_skills:
        return "assigned_with_skill_gap" if item.priority == "high" else "unassigned_skill_gap"
    return "assigned"


def _resolve_manual_employee(
    manual_item: PlanItem | None,
    employees: list[EmployeeRecord],
) -> EmployeeRecord | None:
    if manual_item is None:
        return None
    if manual_item.recommended_assignee_account_id:
        return next(
            (
                employee
                for employee in employees
                if employee.jira_account_id == manual_item.recommended_assignee_account_id
            ),
            None,
        )
    if manual_item.recommended_assignee:
        return next(
            (
                employee
                for employee in employees
                if employee.name.lower() == manual_item.recommended_assignee.lower()
            ),
            None,
        )
    return None


def _rank_employees(
    item: NormalizedTask,
    employees: list[EmployeeRecord],
    remaining: dict[str, int],
) -> list[EmployeeRecord]:
    return sorted(
        employees,
        key=lambda employee: (
            _skill_overlap(item, employee),
            1 if item.owner_hint and employee.name.lower() == item.owner_hint.lower() else 0,
            remaining.get(employee.id, 0),
            employee.name.lower(),
        ),
        reverse=True,
    )


def _build_alternatives(
    item: NormalizedTask,
    employees: list[EmployeeRecord],
    remaining: dict[str, int],
    selected_employee: EmployeeRecord | None,
) -> list[str]:
    alternatives: list[str] = []
    for employee in _rank_employees(item, employees, remaining):
        if selected_employee is not None and employee.id == selected_employee.id:
            continue
        if employee.name in alternatives:
            continue
        alternatives.append(employee.name)
        if len(alternatives) == 2:
            break
    return alternatives


def _build_capacity_summary(
    employees: list[EmployeeRecord],
    assigned_points: defaultdict[str, int],
    plan_items: list[PlanItem],
) -> CapacitySummary:
    allocations = []
    total_capacity = 0
    total_assigned = 0

    for employee in employees:
        assigned = assigned_points.get(employee.id, 0)
        remaining = employee.capacity_points - assigned
        allocations.append(
            MemberCapacitySummary(
                member_name=employee.name,
                capacity_points=employee.capacity_points,
                assigned_points=assigned,
                remaining_points=remaining,
            )
        )
        total_capacity += employee.capacity_points
        total_assigned += assigned

    unassigned_points = sum(
        item.story_points for item in plan_items if item.assignment_status in UNASSIGNED_STATUSES
    )
    return CapacitySummary(
        total_capacity_points=total_capacity,
        assigned_points=total_assigned,
        unassigned_points=unassigned_points,
        remaining_points=total_capacity - total_assigned,
        allocations=allocations,
    )


def _collect_plan_risks(
    plan_items: list[PlanItem],
    capacity_summary: CapacitySummary,
) -> list[RiskFlag]:
    risks: list[RiskFlag] = []
    for item in plan_items:
        risks.extend(item.risk_flags)

    if any(item.assignment_status == "unassigned_capacity" for item in plan_items):
        high_priority_affected = [
            item.task_id
            for item in plan_items
            if item.assignment_status == "unassigned_capacity" and item.priority == "high"
        ]
        risks.append(
            RiskFlag(
                severity="high" if high_priority_affected else "medium",
                category="capacity",
                message=(
                    "Some approved tasks could not be assigned because the roster is out of story-point capacity."
                ),
                affected_items=high_priority_affected,
                suggested_action="Increase capacity, reduce story points, or rebalance ownership before sprint start.",
            )
        )

    if capacity_summary.total_capacity_points > 0:
        utilization = capacity_summary.assigned_points / capacity_summary.total_capacity_points
        if utilization >= 0.9:
            risks.append(
                RiskFlag(
                    severity="medium",
                    category="capacity",
                    message=(
                        "The roster is close to full utilization "
                        f"({capacity_summary.assigned_points}/{capacity_summary.total_capacity_points} pts)."
                    ),
                    affected_items=[],
                    suggested_action="Leave some buffer for interrupts or reconsider lower-priority work.",
                )
            )

    return _dedupe_risks(risks)


def _risk_flags_for_item(item: NormalizedTask, assignment_status: AssignmentStatus) -> list[RiskFlag]:
    if assignment_status == "assigned":
        return []
    if assignment_status == "assigned_with_skill_gap":
        return [
            RiskFlag(
                severity="high",
                category="skill-gap",
                message=(
                    f"{item.task_id} is assigned because it is high priority, but no employee has a clear skill match."
                ),
                affected_items=[item.task_id],
                suggested_action="Review ownership closely or add support from a teammate with the missing skills.",
            )
        ]
    if assignment_status == "unassigned_skill_gap":
        return [
            RiskFlag(
                severity="medium",
                category="skill-gap",
                message=(
                    f"{item.task_id} is left unassigned because the roster does not clearly cover the required skills."
                ),
                affected_items=[item.task_id],
                suggested_action="Add coverage for the missing skills or revise the task scope before sprint start.",
            )
        ]
    return [
        RiskFlag(
            severity="high" if item.priority == "high" else "medium",
            category="capacity",
            message=(
                f"{item.task_id} is left unassigned because no employee has {item.story_points} points remaining."
            ),
            affected_items=[item.task_id],
            suggested_action="Rebalance the sprint, lower the estimate, or accept the task as unassigned in Jira.",
        )
    ]


def _build_plan_epic_fields(plan: SprintPlan) -> dict[str, object]:
    plan_lines = [
        f"- {item.task_id}: {item.title} [{item.jira_issue_type}] ({item.story_points} pts)"
        + (
            f" -> {item.recommended_assignee}"
            if item.assignment_status in ASSIGNED_STATUSES and item.recommended_assignee
            else " -> Unassigned"
        )
        for item in plan.plan_items
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
            "Planned child tickets:",
            *plan_lines,
            "",
            "Roster capacity:",
            *capacity_lines,
            "",
            f"Unassigned approved work: {plan.capacity_summary.unassigned_points} pts",
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


def _build_child_issue_fields(
    item: PlanItem,
    epic_key: str,
    field_requirements: dict[str, object],
    field_service: FieldMetadataService,
) -> dict[str, object]:
    field_requirements = dict(field_requirements)
    draft: dict[str, object] = {
        "summary": item.title,
        "description": item.description,
        "priority": item.priority.capitalize(),
        "labels": _build_item_labels(item),
    }

    story_points_field = field_service.find_story_points_field(field_requirements)
    if story_points_field:
        draft[story_points_field] = item.story_points

    link_field = field_service.find_epic_link_field(field_requirements)
    if link_field is None:
        raise ValueError(
            f"Could not find an Epic parent field for {item.jira_issue_type} creation in Jira metadata."
        )
    if link_field["mode"] == "parent":
        draft[link_field["field_id"]] = {"key": epic_key}
    else:
        draft[link_field["field_id"]] = epic_key

    return draft


def _build_labels(plan: SprintPlan) -> list[str]:
    labels = {"contour"}
    sprint_label = _slugify(plan.sprint_name)
    if sprint_label:
        labels.add(sprint_label)
    for item in plan.plan_items:
        labels.update(_build_item_labels(item))
    return sorted(label for label in labels if label)


def _build_item_labels(item: PlanItem) -> list[str]:
    labels = {"contour", _slugify(item.priority), _slugify(item.jira_issue_type)}
    for skill in item.required_skills:
        labels.add(_slugify(skill))
    return sorted(label for label in labels if label)


def _epic_priority(plan: SprintPlan) -> str:
    if any(risk.severity == "high" for risk in plan.risks):
        return "High"
    if any(item.priority == "high" for item in plan.plan_items):
        return "High"
    return "Medium"


def _assignment_rationale(
    item: NormalizedTask,
    assignment_status: AssignmentStatus,
    employee: EmployeeRecord | None,
    manual_item: PlanItem | None,
) -> str:
    if assignment_status == "assigned" and employee is not None:
        if manual_item is not None and manual_item.recommended_assignee_account_id == employee.jira_account_id:
            return f"Kept the reviewer-selected assignee {employee.name}; the final story-point load still fits."
        matching_skills = [
            skill
            for skill in employee.skills
            if _slugify(skill) in {_slugify(required) for required in item.required_skills}
        ]
        if matching_skills:
            return f"Assigned to {employee.name} because their skills match {', '.join(matching_skills)}."
        return f"Assigned to {employee.name} because they have remaining story-point capacity."
    if assignment_status == "assigned_with_skill_gap" and employee is not None:
        return (
            f"Assigned to {employee.name} because the task is high priority, "
            "even though the roster does not have a clean skill match."
        )
    if assignment_status == "unassigned_skill_gap":
        return "Left unassigned because the available roster does not clearly cover the required skills."
    return "Left unassigned because no employee has enough remaining story-point capacity."


def _default_selection_rationale(item: NormalizedTask) -> str:
    return (
        f"Included because it is part of the approved sprint scope, "
        f"is {item.priority} priority, and is estimated at {item.story_points} story points."
    )


def _sorted_items(items: list[NormalizedTask]) -> list[NormalizedTask]:
    return sorted(
        items,
        key=lambda item: (-PRIORITY_RANK[item.priority], item.source_index),
    )


def _skill_overlap(item: NormalizedTask, employee: EmployeeRecord) -> int:
    required_skills = {_slugify(skill) for skill in item.required_skills}
    employee_skills = {_slugify(skill) for skill in employee.skills}
    if not required_skills:
        return 0
    return len(required_skills & employee_skills)


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


def _normalize_priority(value: object) -> PriorityLevel:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized  # type: ignore[return-value]
    if normalized in {"critical", "highest"}:
        return "high"
    return "medium"


def _normalize_issue_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return "Task" if normalized == "task" else "Story"


def _infer_required_skills(task_text: str, employee_skills: list[str]) -> list[str]:
    normalized_text = _slugify(task_text)
    matches: list[str] = []
    for skill in employee_skills:
        skill_key = _slugify(skill)
        if skill_key and (skill_key in normalized_text or skill_key.replace("-", " ") in task_text.lower()):
            matches.append(skill)
    if matches:
        return sorted({skill for skill in matches})

    heuristics = {
        "frontend": ["frontend", "ui", "react", "web"],
        "backend": ["backend", "api", "service"],
        "jira": ["jira", "atlassian"],
        "integration": ["integration", "handoff", "sync"],
        "ai": ["ai", "llm", "model"],
        "python": ["python", "fastapi"],
        "automation": ["automation", "workflow", "pipeline"],
    }
    return [
        skill
        for skill, keywords in heuristics.items()
        if any(keyword in task_text.lower() for keyword in keywords)
    ]


def _estimate_story_points(task_text: str, required_skills: list[str]) -> int:
    priority = _infer_priority(task_text)
    score = 1
    score += 2 if priority == "high" else 1 if priority == "medium" else 0
    score += min(len(required_skills), 2)
    score += len(
        re.findall(
            r"\b(api|integration|workflow|migration|analytics|auth|dashboard|approval|jira)\b",
            task_text.lower(),
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


def _infer_title(task_text: str) -> str:
    clipped = task_text.strip().split(".")[0]
    words = clipped.split()
    if len(words) <= 8:
        return clipped.rstrip(".")
    return " ".join(words[:8]).rstrip(".")


def _infer_description(task_text: str) -> str:
    text = task_text.strip()
    return text if text.endswith(".") else f"{text}."


def _fallback_estimation_rationale(task_text: str) -> str:
    return (
        "Estimated from the task priority, the implementation complexity implied by the request, "
        f"and the coordination suggested by the task details: {task_text[:80].strip()}."
    )


def _issue_url(base_url: str | None, issue_key: str) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/browse/{issue_key}"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _infer_priority(task_text: str) -> PriorityLevel:
    text = task_text.lower()
    if any(token in text for token in ("urgent", "critical", "immediately", "blocker", "must")):
        return "high"
    if any(token in text for token in ("nice to have", "later", "follow-up", "polish")):
        return "low"
    return "medium"
