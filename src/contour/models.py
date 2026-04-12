from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _require_text(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("must not be empty")
    return value.strip()


def _clean_text_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_text(value)
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


class BacklogItemInput(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    dependencies: list[str] = Field(default_factory=list)
    owner_hint: str | None = None
    labels: list[str] = Field(default_factory=list)

    @field_validator("id", "title", "description", "priority")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("dependencies", "labels", mode="before")
    @classmethod
    def default_list(cls, value: object) -> object:
        return value or []

    @field_validator("dependencies", "labels")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)

    @field_validator("owner_hint")
    @classmethod
    def normalize_owner_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_dependencies(self) -> BacklogItemInput:
        if self.id in self.dependencies:
            raise ValueError("dependencies must not include the item itself")
        return self


class TeamMemberInput(BaseModel):
    name: str
    role: str
    skills: list[str] = Field(min_length=1)
    capacity_points: int = Field(ge=0)

    @field_validator("name", "role")
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
    backlog_items: list[BacklogItemInput] = Field(min_length=1)
    team_members: list[TeamMemberInput] = Field(min_length=1)

    @field_validator("sprint_name", "goal")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @model_validator(mode="after")
    def validate_request_integrity(self) -> SprintRequest:
        backlog_ids = [item.id for item in self.backlog_items]
        duplicate_backlog_ids = _find_case_insensitive_duplicates(backlog_ids)
        if duplicate_backlog_ids:
            raise ValueError(
                f"backlog item ids must be unique; duplicates: {', '.join(duplicate_backlog_ids)}"
            )

        team_member_names = [member.name for member in self.team_members]
        duplicate_member_names = _find_case_insensitive_duplicates(team_member_names)
        if duplicate_member_names:
            raise ValueError(
                f"team member names must be unique; duplicates: {', '.join(duplicate_member_names)}"
            )

        return self


class EnrichedBacklogItem(BacklogItemInput):
    estimated_points: int = Field(ge=1)
    required_skills: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    dependency_signals: list[str] = Field(default_factory=list)
    analysis_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("required_skills", "ambiguity_flags", "dependency_signals", mode="before")
    @classmethod
    def default_derived_lists(cls, value: object) -> object:
        return value or []

    @field_validator("required_skills", "ambiguity_flags", "dependency_signals")
    @classmethod
    def validate_derived_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class SprintPlanItem(EnrichedBacklogItem):
    recommended_assignee: str
    alternative_assignees: list[str] = Field(default_factory=list)
    selection_rationale: str
    assignment_rationale: str

    @field_validator("recommended_assignee", "selection_rationale", "assignment_rationale")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("alternative_assignees", mode="before")
    @classmethod
    def default_alternative_assignees(cls, value: object) -> object:
        return value or []

    @field_validator("alternative_assignees")
    @classmethod
    def validate_alternative_assignees(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)

    @model_validator(mode="after")
    def validate_assignee_lists(self) -> SprintPlanItem:
        if self.recommended_assignee in self.alternative_assignees:
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
    selected_points: int = Field(ge=0)
    remaining_points: int
    allocations: list[MemberCapacitySummary] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_totals(self) -> CapacitySummary:
        total_capacity = sum(allocation.capacity_points for allocation in self.allocations)
        selected_points = sum(allocation.assigned_points for allocation in self.allocations)
        remaining_points = sum(allocation.remaining_points for allocation in self.allocations)

        if self.total_capacity_points != total_capacity:
            raise ValueError(f"total_capacity_points must equal allocation total ({total_capacity})")
        if self.selected_points != selected_points:
            raise ValueError(f"selected_points must equal allocation assigned total ({selected_points})")
        if self.remaining_points != remaining_points:
            raise ValueError(f"remaining_points must equal allocation remaining total ({remaining_points})")

        return self


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


class SprintPlan(BaseModel):
    sprint_name: str
    goal: str
    selected_items: list[SprintPlanItem] = Field(default_factory=list)
    deferred_items: list[EnrichedBacklogItem] = Field(default_factory=list)
    capacity_summary: CapacitySummary
    risks: list[RiskFlag] = Field(default_factory=list)
    approval_state: Literal["draft", "approved"] = "draft"

    @field_validator("sprint_name", "goal")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)

    @model_validator(mode="after")
    def validate_plan_integrity(self) -> SprintPlan:
        selected_ids = {item.id for item in self.selected_items}
        deferred_ids = {item.id for item in self.deferred_items}
        overlap = sorted(selected_ids & deferred_ids)
        if overlap:
            raise ValueError(
                "selected_items and deferred_items must not overlap; duplicate ids: "
                + ", ".join(overlap)
            )
        return self


def _find_case_insensitive_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_keys: set[str] = set()
    for value in values:
        normalized = value.lower()
        if normalized in seen and normalized not in duplicate_keys:
            duplicates.append(value)
            duplicate_keys.add(normalized)
            continue
        seen.add(normalized)
    return duplicates
