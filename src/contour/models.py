from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


STORY_POINT_BUCKETS = (1, 2, 3, 5, 8)

PriorityLevel = Literal["low", "medium", "high"]
IssueTypeName = Literal["Story", "Task"]
AssignmentStatus = Literal[
    "assigned",
    "unassigned_capacity",
    "unassigned_skill_gap",
    "assigned_with_skill_gap",
]


def _require_text(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("must not be empty")
    return value.strip()


def _clean_text_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_text(value)
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


class TaskInput(BaseModel):
    text: str
    owner_hint: str | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("owner_hint")
    @classmethod
    def normalize_owner_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class EmployeeRecord(BaseModel):
    id: str
    name: str
    role: str
    skills: list[str] = Field(min_length=1)
    capacity_points: int = Field(ge=0)
    jira_account_id: str

    @field_validator("id", "name", "role", "jira_account_id")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        cleaned = _clean_text_list(value)
        if not cleaned:
            raise ValueError("must include at least one skill")
        return cleaned


class SprintRequest(BaseModel):
    sprint_name: str
    goal: str
    tasks: list[TaskInput] = Field(min_length=1)

    @field_validator("sprint_name", "goal")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @model_validator(mode="after")
    def validate_request_integrity(self) -> SprintRequest:
        task_texts = [task.text for task in self.tasks]
        duplicate_tasks = _find_case_insensitive_duplicates(task_texts)
        if duplicate_tasks:
            raise ValueError(
                f"tasks must be unique; duplicates: {', '.join(duplicate_tasks)}"
            )
        return self


class NormalizedTask(BaseModel):
    task_id: str
    source_index: int = Field(ge=0)
    task_text: str
    owner_hint: str | None = None
    title: str
    description: str
    priority: PriorityLevel
    jira_issue_type: IssueTypeName
    story_points: int = Field(ge=1)
    required_skills: list[str] = Field(default_factory=list)
    estimation_rationale: str

    @field_validator("task_id", "task_text", "title", "description", "estimation_rationale")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("owner_hint")
    @classmethod
    def normalize_owner_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("required_skills", mode="before")
    @classmethod
    def default_required_skills(cls, value: object) -> object:
        return value or []

    @field_validator("required_skills")
    @classmethod
    def validate_required_skills(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)

    @field_validator("story_points")
    @classmethod
    def validate_story_points(cls, value: int) -> int:
        if value not in STORY_POINT_BUCKETS:
            raise ValueError(
                f"story_points must be one of {', '.join(str(bucket) for bucket in STORY_POINT_BUCKETS)}"
            )
        return value


class RiskFlag(BaseModel):
    severity: Literal["low", "medium", "high"]
    category: str
    message: str
    affected_items: list[str] = Field(default_factory=list)
    suggested_action: str

    @field_validator("category", "message", "suggested_action")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("affected_items", mode="before")
    @classmethod
    def default_affected_items(cls, value: object) -> object:
        return value or []

    @field_validator("affected_items")
    @classmethod
    def validate_affected_items(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class PlanItem(NormalizedTask):
    recommended_assignee: str | None = None
    recommended_assignee_account_id: str | None = None
    alternative_assignees: list[str] = Field(default_factory=list)
    assignment_status: AssignmentStatus
    selection_rationale: str
    assignment_rationale: str
    risk_flags: list[RiskFlag] = Field(default_factory=list)

    @field_validator("recommended_assignee", "recommended_assignee_account_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("selection_rationale", "assignment_rationale")
    @classmethod
    def validate_required_rationales(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("alternative_assignees", mode="before")
    @classmethod
    def default_alternative_assignees(cls, value: object) -> object:
        return value or []

    @field_validator("alternative_assignees")
    @classmethod
    def validate_alternative_assignees(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)

    @field_validator("risk_flags", mode="before")
    @classmethod
    def default_risk_flags(cls, value: object) -> object:
        return value or []

    @model_validator(mode="after")
    def validate_assignment_fields(self) -> PlanItem:
        assigned_statuses = {"assigned", "assigned_with_skill_gap"}
        if self.assignment_status in assigned_statuses:
            if not self.recommended_assignee or not self.recommended_assignee_account_id:
                raise ValueError("assigned items must include assignee name and Jira account id")
        else:
            if self.recommended_assignee or self.recommended_assignee_account_id:
                raise ValueError("unassigned items must not include assignee details")
        if self.recommended_assignee and self.recommended_assignee in self.alternative_assignees:
            raise ValueError("alternative assignees must not include the recommended assignee")
        return self


class MemberCapacitySummary(BaseModel):
    member_name: str
    capacity_points: int = Field(ge=0)
    assigned_points: int = Field(ge=0)
    remaining_points: int

    @field_validator("member_name")
    @classmethod
    def validate_member_name(cls, value: str) -> str:
        return _require_text(value)

    @model_validator(mode="after")
    def validate_capacity_math(self) -> MemberCapacitySummary:
        expected_remaining = self.capacity_points - self.assigned_points
        if self.remaining_points != expected_remaining:
            raise ValueError(
                f"remaining_points must equal capacity_points - assigned_points ({expected_remaining})"
            )
        return self


class CapacitySummary(BaseModel):
    total_capacity_points: int = Field(ge=0)
    assigned_points: int = Field(ge=0)
    unassigned_points: int = Field(ge=0)
    remaining_points: int
    allocations: list[MemberCapacitySummary] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_totals(self) -> CapacitySummary:
        total_capacity = sum(allocation.capacity_points for allocation in self.allocations)
        assigned_points = sum(allocation.assigned_points for allocation in self.allocations)
        remaining_points = sum(allocation.remaining_points for allocation in self.allocations)

        if self.total_capacity_points != total_capacity:
            raise ValueError(f"total_capacity_points must equal allocation total ({total_capacity})")
        if self.assigned_points != assigned_points:
            raise ValueError(f"assigned_points must equal allocation assigned total ({assigned_points})")
        if self.remaining_points != remaining_points:
            raise ValueError(f"remaining_points must equal allocation remaining total ({remaining_points})")

        return self


class SprintPlan(BaseModel):
    sprint_name: str
    goal: str
    plan_items: list[PlanItem] = Field(default_factory=list)
    capacity_summary: CapacitySummary
    risks: list[RiskFlag] = Field(default_factory=list)
    approval_state: Literal["draft", "approved"] = "draft"

    @field_validator("sprint_name", "goal")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("risks", mode="before")
    @classmethod
    def default_risks(cls, value: object) -> object:
        return value or []

    @model_validator(mode="after")
    def validate_plan_integrity(self) -> SprintPlan:
        task_ids = [item.task_id for item in self.plan_items]
        duplicate_task_ids = _find_case_insensitive_duplicates(task_ids)
        if duplicate_task_ids:
            raise ValueError(
                f"plan_items must have unique task_id values; duplicates: {', '.join(duplicate_task_ids)}"
            )
        return self


class JiraIssueResult(BaseModel):
    key: str
    url: str | None = None
    summary: str
    issue_type: IssueTypeName
    assignment_status: AssignmentStatus
    assignee: str | None = None

    @field_validator("key", "summary")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)


class JiraHandoffResult(BaseModel):
    key: str
    url: str | None = None
    issues: list[JiraIssueResult] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)


def _find_case_insensitive_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_keys: set[str] = set()
    for value in values:
        normalized = value.lower()
        if normalized in seen and normalized not in duplicate_keys:
            duplicates.append(value)
            duplicate_keys.add(normalized)
        seen.add(normalized)
    return duplicates
