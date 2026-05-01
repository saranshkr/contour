from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import time

from contour.jira_client import JiraClient
from contour.models import (
    AssignmentStatus,
    CapacitySummary,
    EmployeeRecord,
    EngineerProfile,
    JiraDryRunResponse,
    JiraHandoffResult,
    JiraIssuePreview,
    JiraIssueResult,
    JiraSyncState,
    JiraSyncStatus,
    MemberCapacitySummary,
    NormalizedTask,
    PlanItem,
    PriorityLevel,
    RiskFlag,
    SprintPlan,
    SprintPlanInput,
    TeamCapacity,
)
from contour.sample_data import build_employee_roster
from contour.services.constraint_validator import validate_sprint_input, validate_sprint_plan
from contour.services.epic_handler import EpicCreationHandler
from contour.services.field_meta import FieldMetadataService
from contour.services.jira_sync_store import JiraSyncStore
from contour.services.llm import LLMService

PRIORITY_RANK: dict[PriorityLevel, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}

ASSIGNED_STATUSES = {"assigned", "assigned_with_skill_gap"}
UNASSIGNED_STATUSES = {"unassigned_capacity", "unassigned_skill_gap"}


def plan_sprint(
    request: SprintPlanInput,
    llm_service: LLMService | None = None,
) -> SprintPlan:
    employees = _resolve_employees(request.engineer_profiles)
    llm = llm_service or LLMService()
    input_validation = validate_sprint_input(request, employees)
    normalized_items = _repair_normalized_tasks(
        request=request,
        employees=employees,
        normalized_items=llm.normalize_tasks(request, employees),
    )
    plan = _build_plan(
        sprint_name=request.sprint_name,
        goal=request.goal,
        normalized_items=normalized_items,
        employees=employees,
        team_capacity=request.team_capacity,
        engineer_profiles=request.engineer_profiles,
        approval_state="draft",
    )
    validation = validate_sprint_plan(plan, employees, request.team_capacity)
    if input_validation.errors or input_validation.warnings:
        validation.errors = [*input_validation.errors, *validation.errors]
        validation.warnings = [*input_validation.warnings, *validation.warnings]
        validation.is_valid = not validation.errors
    plan.validation_result = validation
    return plan


def approve_plan(
    plan: SprintPlan,
    engineers: list[EngineerProfile] | None = None,
    team_capacity: TeamCapacity | None = None,
) -> SprintPlan:
    resolved_engineers = engineers if engineers is not None else plan.engineer_profiles
    resolved_team_capacity = team_capacity if team_capacity is not None else plan.team_capacity
    employees = _resolve_employees(resolved_engineers)
    normalized_items = [_normalized_from_plan_item(item) for item in plan.plan_items]
    plan_by_task_id = {item.task_id: item for item in plan.plan_items}
    repaired = _build_plan(
        sprint_name=plan.sprint_name,
        goal=plan.goal,
        normalized_items=normalized_items,
        employees=employees,
        team_capacity=resolved_team_capacity,
        engineer_profiles=resolved_engineers,
        manual_items=plan_by_task_id,
        approval_state="approved",
    )
    repaired.validation_result = validate_sprint_plan(repaired, employees, resolved_team_capacity)
    if not repaired.validation_result.is_valid:
        raise ValueError("Sprint plan validation failed. Resolve errors before approval.")
    return repaired


def dry_run_plan_handoff(
    project_key: str,
    plan: SprintPlan,
    jira_client: JiraClient | None = None,
    engineers: list[EngineerProfile] | None = None,
    team_capacity: TeamCapacity | None = None,
    sync_store: JiraSyncStore | None = None,
    accept_warnings: bool = False,
) -> JiraDryRunResponse:
    jira = jira_client or JiraClient()
    store = sync_store or JiraSyncStore()
    resolved_engineers = engineers if engineers is not None else plan.engineer_profiles
    resolved_team_capacity = team_capacity if team_capacity is not None else plan.team_capacity
    employees = _resolve_employees(resolved_engineers)
    idempotency_key = build_idempotency_key(project_key, plan)
    sync_state = store.get(idempotency_key) or JiraSyncState(
        idempotency_key=idempotency_key,
        project_key=project_key,
        status=JiraSyncStatus.NOT_STARTED,
    )

    field_service = FieldMetadataService(jira)
    handler = EpicCreationHandler(jira, field_service)
    epic_preview, child_previews = _build_jira_previews(project_key, plan, handler, field_service)
    validation = validate_sprint_plan(
        plan,
        employees,
        resolved_team_capacity,
        jira_previews=[epic_preview, *child_previews],
    )

    warnings_accepted = accept_warnings or not validation.warnings
    safe_to_execute = validation.is_valid and warnings_accepted
    sync_state.status = JiraSyncStatus.DRY_RUN_PASSED if safe_to_execute else JiraSyncStatus.NOT_STARTED
    sync_state.validation_errors = validation.errors
    sync_state.validation_warnings = validation.warnings
    if safe_to_execute:
        sync_state.last_error = None
    elif validation.is_valid and validation.warnings:
        sync_state.last_error = "Dry run warnings must be explicitly accepted."
    else:
        sync_state.last_error = "Dry run validation failed."
    store.save(sync_state)

    return JiraDryRunResponse(
        idempotency_key=idempotency_key,
        epic_payload_preview=epic_preview,
        child_issue_payload_previews=child_previews,
        validation_errors=validation.errors,
        validation_warnings=validation.warnings,
        estimated_jira_objects=1 + len(child_previews),
        safe_to_execute=safe_to_execute,
        sync_state=sync_state,
    )


def create_plan_epic(
    project_key: str,
    approved_plan: SprintPlan,
    jira_client: JiraClient | None = None,
    engineers: list[EngineerProfile] | None = None,
    team_capacity: TeamCapacity | None = None,
    sync_store: JiraSyncStore | None = None,
    accept_warnings: bool = False,
) -> JiraHandoffResult:
    if approved_plan.approval_state != "approved":
        raise ValueError("Sprint plan must be approved before Jira handoff.")

    jira = jira_client or JiraClient()
    store = sync_store or JiraSyncStore()
    resolved_engineers = engineers if engineers is not None else approved_plan.engineer_profiles
    resolved_team_capacity = team_capacity if team_capacity is not None else approved_plan.team_capacity
    employees = _resolve_employees(resolved_engineers)
    dry_run = dry_run_plan_handoff(
        project_key=project_key,
        plan=approved_plan,
        jira_client=jira,
        engineers=employees,
        team_capacity=resolved_team_capacity,
        sync_store=store,
        accept_warnings=accept_warnings,
    )
    if not dry_run.safe_to_execute:
        raise ValueError("Jira dry-run validation failed. Resolve errors before Jira handoff.")

    sync_state = dry_run.sync_state
    if sync_state.status == JiraSyncStatus.SYNC_SUCCEEDED and sync_state.epic_key:
        return _result_from_sync_state(jira.base_url, approved_plan, sync_state)

    field_service = FieldMetadataService(jira)
    handler = EpicCreationHandler(jira, field_service)
    sync_state.status = JiraSyncStatus.SYNC_IN_PROGRESS
    store.save(sync_state)

    try:
        if not sync_state.epic_key:
            epic_preview, child_previews = _build_jira_previews(project_key, approved_plan, handler, field_service)
            epic_key = handler.create_epic(project_key, epic_preview.fields)
            sync_state.epic_key = epic_key
            store.save(sync_state)
        else:
            epic_key = sync_state.epic_key
            _, child_previews = _build_jira_previews(project_key, approved_plan, handler, field_service, epic_key)

        issues: list[JiraIssueResult] = []
        for preview, item in zip(child_previews, approved_plan.plan_items):
            existing_key = sync_state.child_issue_keys.get(item.task_id)
            if existing_key is None:
                created_key = handler.create_issue(project_key, item.jira_issue_type, preview.fields)
                sync_state.child_issue_keys[item.task_id] = created_key
                store.save(sync_state)
                issue_key = created_key
            else:
                issue_key = existing_key
            issues.append(
                JiraIssueResult(
                    key=issue_key,
                    url=_issue_url(jira.base_url, issue_key),
                    summary=item.title,
                    issue_type=item.jira_issue_type,
                    assignment_status=item.assignment_status,
                    assignee=item.recommended_assignee,
                    task_id=item.task_id,
                )
            )
    except Exception as exc:
        sync_state.status = (
            JiraSyncStatus.PARTIAL_FAILURE if sync_state.epic_key or sync_state.child_issue_keys else JiraSyncStatus.SYNC_FAILED
        )
        sync_state.last_error = str(exc)
        store.save(sync_state)
        raise

    sync_state.status = JiraSyncStatus.SYNC_SUCCEEDED
    sync_state.last_error = None
    store.save(sync_state)
    return JiraHandoffResult(
        key=epic_key,
        url=_issue_url(jira.base_url, epic_key),
        issues=issues,
        sync_state=sync_state,
    )


def build_idempotency_key(project_key: str, plan: SprintPlan) -> str:
    payload = json.dumps(
        {
            "project_key": project_key.upper(),
            "plan": plan.model_dump(mode="json", exclude={"validation_result"}),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{project_key.upper()}-{digest[:20]}"


def _resolve_employees(engineers: list[EngineerProfile] | None) -> list[EmployeeRecord]:
    if engineers:
        return [EmployeeRecord.model_validate(engineer.model_dump()) for engineer in engineers]
    return build_employee_roster()


def _build_jira_previews(
    project_key: str,
    plan: SprintPlan,
    handler: EpicCreationHandler,
    field_service: FieldMetadataService,
    epic_key: str | None = None,
) -> tuple[JiraIssuePreview, list[JiraIssuePreview]]:
    field_requirements = field_service.get_epic_fields(project_key)
    account_id = field_service.get_user_id()
    draft_fields = _build_plan_epic_fields(plan)
    mapped_fields = handler.map_fields(draft_fields, field_requirements, account_id)
    epic_preview = JiraIssuePreview(issue_type="Epic", fields=mapped_fields)

    child_previews: list[JiraIssuePreview] = []
    parent_epic_key = epic_key or "DRY-RUN-EPIC"
    for item in plan.plan_items:
        issue_fields = field_service.get_issue_type_fields(project_key, item.jira_issue_type)
        child_draft = _build_child_issue_fields(
            item=item,
            epic_key=parent_epic_key,
            field_requirements=issue_fields,
            field_service=field_service,
        )
        mapped_child = handler.map_fields(child_draft, issue_fields, account_id)
        if item.assignment_status in ASSIGNED_STATUSES and item.recommended_assignee_account_id:
            mapped_child["assignee"] = {"id": item.recommended_assignee_account_id}
        child_previews.append(
            JiraIssuePreview(
                issue_type=item.jira_issue_type,
                fields=mapped_child,
                task_id=item.task_id,
            )
        )
    return epic_preview, child_previews


def _build_plan(
    sprint_name: str,
    goal: str,
    normalized_items: list[NormalizedTask],
    employees: list[EmployeeRecord],
    team_capacity: TeamCapacity | None = None,
    engineer_profiles: list[EngineerProfile] | None = None,
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
    plan = SprintPlan(
        sprint_name=sprint_name,
        goal=goal,
        plan_items=built_items,
        capacity_summary=capacity_summary,
        risks=risks,
        approval_state=approval_state,
        engineer_profiles=engineer_profiles or employees,
        team_capacity=team_capacity,
    )
    plan.validation_result = validate_sprint_plan(plan, employees, team_capacity)
    return plan


def _repair_normalized_tasks(
    request: SprintPlanInput,
    employees: list[EmployeeRecord],
    normalized_items: list[NormalizedTask],
) -> list[NormalizedTask]:
    employee_skills = [skill for employee in employees for skill in employee.skills]
    repaired: list[NormalizedTask] = []
    for index, task in enumerate(request.backlog_items):
        if index < len(normalized_items):
            item = normalized_items[index]
            raw = item.model_dump()
        else:
            raw = {}

        task_text = task.text or " ".join(filter(None, [task.title, task.description]))
        required_skills = raw.get("required_skills") or _infer_required_skills(task_text, employee_skills)
        story_points = raw.get("story_points")
        if story_points not in {1, 2, 3, 5, 8}:
            story_points = _estimate_story_points(task_text, required_skills)

        repaired.append(
            NormalizedTask(
                task_id=f"TASK-{index + 1}",
                source_index=index,
                task_text=task_text,
                owner_hint=task.owner_hint,
                backlog_item_id=task.id,
                title=raw.get("title") or task.title or _infer_title(task_text),
                description=raw.get("description") or task.description or _infer_description(task_text),
                acceptance_criteria=raw.get("acceptance_criteria") or task.acceptance_criteria,
                priority=_normalize_priority(raw.get("priority") or task.priority),
                jira_issue_type=_normalize_issue_type(raw.get("jira_issue_type") or task.task_type),
                status=raw.get("status") or task.status or "todo",
                story_points=story_points,
                required_skills=required_skills,
                estimation_rationale=raw.get("estimation_rationale")
                or _fallback_estimation_rationale(task_text),
            )
        )
    return repaired


def _normalized_from_plan_item(item: PlanItem) -> NormalizedTask:
    return NormalizedTask(
        task_id=item.task_id,
        source_index=item.source_index,
        task_text=item.task_text,
        owner_hint=item.owner_hint,
        backlog_item_id=item.backlog_item_id,
        title=item.title,
        description=item.description,
        acceptance_criteria=item.acceptance_criteria,
        priority=item.priority,
        jira_issue_type=item.jira_issue_type,
        status=item.status,
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
    criteria_block = (
        "\n\nAcceptance criteria:\n" + "\n".join(f"- {criterion}" for criterion in item.acceptance_criteria)
        if item.acceptance_criteria
        else ""
    )
    draft: dict[str, object] = {
        "summary": item.title,
        "description": f"{item.description}{criteria_block}",
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
    return f"Selected from the draft because it supports the sprint goal and is scoped as a {item.jira_issue_type.lower()}."


def _sorted_items(items: list[NormalizedTask]) -> list[NormalizedTask]:
    return sorted(
        items,
        key=lambda item: (
            PRIORITY_RANK[item.priority],
            item.story_points,
            -item.source_index,
        ),
        reverse=True,
    )


def _skill_overlap(item: NormalizedTask, employee: EmployeeRecord) -> int:
    required = {_slugify(skill) for skill in item.required_skills}
    available = {_slugify(skill) for skill in employee.skills}
    return len(required & available)


def _infer_required_skills(task_text: str, employee_skills: list[str]) -> list[str]:
    task_tokens = {_slugify(token) for token in re.split(r"[^a-zA-Z0-9.+#]+", task_text) if token}
    matches = []
    for skill in employee_skills:
        skill_key = _slugify(skill)
        if skill_key in task_tokens:
            matches.append(skill)
    return sorted(set(matches))


def _estimate_story_points(task_text: str, required_skills: list[str]) -> int:
    word_count = len(task_text.split())
    complexity = len(required_skills)
    if word_count > 40 or complexity >= 3:
        return 8
    if word_count > 28 or complexity == 2:
        return 5
    if word_count > 16:
        return 3
    if word_count > 8:
        return 2
    return 1


def _infer_title(task_text: str) -> str:
    sentence = task_text.strip().rstrip(".")
    if len(sentence) <= 72:
        return sentence
    return sentence[:69].rstrip() + "..."


def _infer_description(task_text: str) -> str:
    return task_text.strip()


def _fallback_estimation_rationale(task_text: str) -> str:
    return f"Estimated from task wording, scope, and likely implementation complexity: {task_text.strip()}"


def _normalize_priority(value: str | None) -> PriorityLevel:
    normalized = (value or "medium").strip().lower()
    return "high" if normalized not in {"low", "medium", "high"} else normalized  # type: ignore[return-value]


def _normalize_issue_type(value: str | None) -> str:
    normalized = (value or "Task").strip().lower()
    return "Story" if normalized == "story" else "Task"


def _dedupe_risks(risks: list[RiskFlag]) -> list[RiskFlag]:
    deduped: list[RiskFlag] = []
    seen: set[tuple[str, str]] = set()
    for risk in risks:
        key = (risk.category.lower(), risk.message.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _issue_url(base_url: str, issue_key: str) -> str:
    return f"{base_url}/browse/{issue_key}"


def _result_from_sync_state(base_url: str, plan: SprintPlan, sync_state: JiraSyncState) -> JiraHandoffResult:
    issues = [
        JiraIssueResult(
            key=sync_state.child_issue_keys[item.task_id],
            url=_issue_url(base_url, sync_state.child_issue_keys[item.task_id]),
            summary=item.title,
            issue_type=item.jira_issue_type,
            assignment_status=item.assignment_status,
            assignee=item.recommended_assignee,
            task_id=item.task_id,
        )
        for item in plan.plan_items
        if item.task_id in sync_state.child_issue_keys
    ]
    return JiraHandoffResult(
        key=sync_state.epic_key or "UNKNOWN",
        url=_issue_url(base_url, sync_state.epic_key or "UNKNOWN"),
        issues=issues,
        sync_state=sync_state,
    )
