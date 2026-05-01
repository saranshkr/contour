from __future__ import annotations

from collections import defaultdict

from contour.models import (
    BacklogItem,
    EngineerProfile,
    JiraIssuePreview,
    SprintPlan,
    SprintPlanInput,
    SprintPlanValidationResult,
    TeamCapacity,
    ValidationMessage,
    ValidationMetrics,
    VALID_PRIORITY_LEVELS,
    VALID_TASK_TYPES,
    VALID_WORK_ITEM_STATUS_VALUES,
)


ASSIGNED_STATUSES = {"assigned", "assigned_with_skill_gap"}


def validate_sprint_input(
    request: SprintPlanInput,
    engineers: list[EngineerProfile],
) -> SprintPlanValidationResult:
    errors: list[ValidationMessage] = []
    warnings: list[ValidationMessage] = []

    backlog_ids = [item.id for item in request.backlog_items if item.id]
    duplicates = _find_duplicates(backlog_ids)
    for duplicate in duplicates:
        errors.append(
            ValidationMessage(
                code="duplicate_backlog_item_id",
                message=f"Duplicate backlog item ID '{duplicate}' detected.",
                field="backlog_items.id",
                task_id=duplicate,
            )
        )

    for index, item in enumerate(request.backlog_items):
        task_id = item.id or f"INPUT-{index + 1}"
        _validate_backlog_item(item, task_id, errors, warnings)

    metrics = _build_metrics([], engineers, request.team_capacity)
    return SprintPlanValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )


def validate_sprint_plan(
    plan: SprintPlan,
    engineers: list[EngineerProfile],
    team_capacity: TeamCapacity | None = None,
    jira_previews: list[JiraIssuePreview] | None = None,
) -> SprintPlanValidationResult:
    errors: list[ValidationMessage] = []
    warnings: list[ValidationMessage] = []
    engineer_by_name = {engineer.name.lower(): engineer for engineer in engineers}
    assigned_points_by_engineer: defaultdict[str, int] = defaultdict(int)

    task_ids = [item.backlog_item_id for item in plan.plan_items if item.backlog_item_id]
    for duplicate in _find_duplicates(task_ids):
        errors.append(
            ValidationMessage(
                code="duplicate_backlog_item_id",
                message=f"Duplicate backlog item ID '{duplicate}' detected in the plan.",
                field="plan_items.backlog_item_id",
                task_id=duplicate,
            )
        )

    for item in plan.plan_items:
        if item.story_points not in {1, 2, 3, 5, 8}:
            errors.append(
                ValidationMessage(
                    code="invalid_story_points",
                    message=f"{item.task_id} has invalid story points '{item.story_points}'.",
                    field="story_points",
                    task_id=item.task_id,
                )
            )

        if not item.title.strip():
            errors.append(
                ValidationMessage(
                    code="missing_task_title",
                    message=f"{item.task_id} is missing a task title.",
                    field="title",
                    task_id=item.task_id,
                )
            )

        if not item.description.strip():
            errors.append(
                ValidationMessage(
                    code="missing_task_description",
                    message=f"{item.task_id} is missing a task description.",
                    field="description",
                    task_id=item.task_id,
                )
            )

        if item.jira_issue_type not in VALID_TASK_TYPES:
            errors.append(
                ValidationMessage(
                    code="unsupported_task_type",
                    message=f"{item.task_id} uses unsupported task type '{item.jira_issue_type}'.",
                    field="jira_issue_type",
                    task_id=item.task_id,
                )
            )

        if item.priority not in VALID_PRIORITY_LEVELS:
            errors.append(
                ValidationMessage(
                    code="invalid_priority",
                    message=f"{item.task_id} uses invalid priority '{item.priority}'.",
                    field="priority",
                    task_id=item.task_id,
                )
            )

        if item.status not in VALID_WORK_ITEM_STATUS_VALUES:
            errors.append(
                ValidationMessage(
                    code="invalid_status",
                    message=f"{item.task_id} uses invalid status '{item.status}'.",
                    field="status",
                    task_id=item.task_id,
                )
            )

        if not item.acceptance_criteria:
            warnings.append(
                ValidationMessage(
                    code="missing_acceptance_criteria",
                    message=f"{item.task_id} has no acceptance criteria.",
                    field="acceptance_criteria",
                    task_id=item.task_id,
                )
            )

        if item.recommended_assignee:
            engineer = engineer_by_name.get(item.recommended_assignee.lower())
            if engineer is None:
                errors.append(
                    ValidationMessage(
                        code="unknown_owner",
                        message=f"{item.task_id} is assigned to '{item.recommended_assignee}', who is not in the roster.",
                        field="recommended_assignee",
                        task_id=item.task_id,
                    )
                )
            else:
                assigned_points_by_engineer[engineer.id] += item.story_points
                if item.required_skills and not _has_matching_skill(item.required_skills, engineer.skills):
                    warnings.append(
                        ValidationMessage(
                            code="owner_skill_gap",
                            message=f"{item.task_id} is assigned to {engineer.name} without a matching skill profile.",
                            field="recommended_assignee",
                            task_id=item.task_id,
                        )
                    )

    total_points = sum(item.story_points for item in plan.plan_items)
    available_capacity = _available_capacity(engineers, team_capacity)
    if total_points > available_capacity:
        errors.append(
            ValidationMessage(
                code="total_points_exceed_capacity",
                message=(
                    f"Total sprint points ({total_points}) exceed available capacity ({available_capacity})."
                ),
                field="capacity_summary",
            )
        )

    overloaded_engineers: list[str] = []
    for engineer in engineers:
        assigned_points = assigned_points_by_engineer.get(engineer.id, 0)
        if assigned_points > engineer.capacity_points:
            overloaded_engineers.append(engineer.name)
            errors.append(
                ValidationMessage(
                    code="overloaded_engineer",
                    message=(
                        f"{engineer.name} is overloaded at {assigned_points}/{engineer.capacity_points} points."
                    ),
                    field="recommended_assignee",
                )
            )

    if jira_previews:
        errors.extend(_validate_jira_previews(jira_previews))

    metrics = _build_metrics(plan.plan_items, engineers, team_capacity, overloaded_engineers)
    return SprintPlanValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )


def _validate_backlog_item(
    item: BacklogItem,
    task_id: str,
    errors: list[ValidationMessage],
    warnings: list[ValidationMessage],
) -> None:
    if not (item.text or item.title):
        errors.append(
            ValidationMessage(
                code="missing_task_title",
                message=f"{task_id} is missing task text or title.",
                field="text",
                task_id=task_id,
            )
        )

    if not (item.description or item.text):
        errors.append(
            ValidationMessage(
                code="missing_task_description",
                message=f"{task_id} is missing task description.",
                field="description",
                task_id=task_id,
            )
        )

    if item.task_type is not None and item.task_type not in VALID_TASK_TYPES:
        errors.append(
            ValidationMessage(
                code="unsupported_task_type",
                message=f"{task_id} uses unsupported task type '{item.task_type}'.",
                field="task_type",
                task_id=task_id,
            )
        )

    if item.priority is not None and item.priority not in VALID_PRIORITY_LEVELS:
        errors.append(
            ValidationMessage(
                code="invalid_priority",
                message=f"{task_id} uses invalid priority '{item.priority}'.",
                field="priority",
                task_id=task_id,
            )
        )

    if item.status is not None and item.status not in VALID_WORK_ITEM_STATUS_VALUES:
        errors.append(
            ValidationMessage(
                code="invalid_status",
                message=f"{task_id} uses invalid status '{item.status}'.",
                field="status",
                task_id=task_id,
            )
        )

    if not item.acceptance_criteria:
        warnings.append(
            ValidationMessage(
                code="missing_acceptance_criteria",
                message=f"{task_id} has no acceptance criteria.",
                field="acceptance_criteria",
                task_id=task_id,
            )
        )


def _validate_jira_previews(previews: list[JiraIssuePreview]) -> list[ValidationMessage]:
    errors: list[ValidationMessage] = []
    for preview in previews:
        summary = preview.fields.get("summary")
        description = preview.fields.get("description")
        if not isinstance(summary, str) or not summary.strip():
            errors.append(
                ValidationMessage(
                    code="malformed_jira_payload",
                    message=f"{preview.issue_type} payload is missing a summary.",
                    field="summary",
                    task_id=preview.task_id,
                )
            )
        if not isinstance(description, str) or not description.strip():
            errors.append(
                ValidationMessage(
                    code="malformed_jira_payload",
                    message=f"{preview.issue_type} payload is missing a description.",
                    field="description",
                    task_id=preview.task_id,
                )
            )
    return errors


def _available_capacity(
    engineers: list[EngineerProfile],
    team_capacity: TeamCapacity | None,
) -> int:
    roster_capacity = sum(engineer.capacity_points for engineer in engineers)
    if team_capacity is None:
        return roster_capacity
    override = team_capacity.available_points if team_capacity.available_points is not None else roster_capacity
    return max(override - team_capacity.buffer_points, 0)


def _build_metrics(
    plan_items: list,
    engineers: list[EngineerProfile],
    team_capacity: TeamCapacity | None,
    overloaded_engineers: list[str] | None = None,
) -> ValidationMetrics:
    overloaded_engineers = overloaded_engineers or []
    total_points = sum(item.story_points for item in plan_items)
    available_capacity = _available_capacity(engineers, team_capacity)
    utilization = (total_points / available_capacity) if available_capacity else 0
    assigned_item_count = sum(1 for item in plan_items if item.assignment_status in ASSIGNED_STATUSES)
    unassigned_item_count = len(plan_items) - assigned_item_count
    return ValidationMetrics(
        total_points=total_points,
        available_capacity=available_capacity,
        capacity_utilization=round(utilization, 4),
        overloaded_engineers=overloaded_engineers,
        assigned_item_count=assigned_item_count,
        unassigned_item_count=unassigned_item_count,
    )


def _find_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_keys: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen and key not in duplicate_keys:
            duplicates.append(value)
            duplicate_keys.add(key)
        seen.add(key)
    return duplicates


def _has_matching_skill(required_skills: list[str], engineer_skills: list[str]) -> bool:
    normalized_required = {skill.lower() for skill in required_skills}
    normalized_engineer = {skill.lower() for skill in engineer_skills}
    return bool(normalized_required & normalized_engineer)
