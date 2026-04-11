from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _require_text(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("must not be empty")
    return value.strip()


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

    @field_validator("owner_hint")
    @classmethod
    def normalize_owner_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


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
        cleaned = [_require_text(skill) for skill in value]
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


class EnrichedBacklogItem(BacklogItemInput):
    estimated_points: int = Field(ge=1)
    required_skills: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    dependency_signals: list[str] = Field(default_factory=list)
    analysis_confidence: float = Field(ge=0.0, le=1.0)


class SprintPlanItem(EnrichedBacklogItem):
    recommended_assignee: str
    alternative_assignees: list[str] = Field(default_factory=list)
    selection_rationale: str
    assignment_rationale: str

    @field_validator("recommended_assignee", "selection_rationale", "assignment_rationale")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_text(value)


class MemberCapacitySummary(BaseModel):
    member_name: str
    capacity_points: int = Field(ge=0)
    assigned_points: int = Field(ge=0)
    remaining_points: int


class CapacitySummary(BaseModel):
    total_capacity_points: int = Field(ge=0)
    selected_points: int = Field(ge=0)
    remaining_points: int
    allocations: list[MemberCapacitySummary] = Field(default_factory=list)


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
