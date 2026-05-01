from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from contour.jira_client import JiraError
from contour.models import (
    EmployeeRecord,
    JiraDryRunRequest,
    JiraDryRunResponse,
    JiraHandoffRequest,
    JiraHandoffResult,
    SprintPlan,
    SprintPlanActionRequest,
    SprintRequest,
)
from contour.orchestrator import approve_plan, create_plan_epic, dry_run_plan_handoff, plan_sprint
from contour.sample_data import build_employee_roster, build_sample_request


def _allowed_origins() -> list[str]:
    configured = os.getenv("CONTOUR_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Contour API",
        version="0.1.0",
        summary="HTTP interface for sprint planning and Jira handoff.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/sample-request", response_model=SprintRequest)
    def get_sample_request() -> SprintRequest:
        return build_sample_request()

    @app.get("/api/v1/employees", response_model=list[EmployeeRecord])
    def get_employees() -> list[EmployeeRecord]:
        return build_employee_roster()

    @app.post("/api/v1/plans/generate", response_model=SprintPlan)
    def generate_plan(request: SprintRequest) -> SprintPlan:
        return plan_sprint(request)

    @app.post("/api/v1/plans/approve", response_model=SprintPlan)
    def approve_draft(payload: SprintPlan | SprintPlanActionRequest) -> SprintPlan:
        try:
            if isinstance(payload, SprintPlan):
                return approve_plan(payload)
            return approve_plan(
                payload.plan,
                engineers=_resolve_payload_engineers(payload),
                team_capacity=_resolve_payload_team_capacity(payload),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/jira/dry-run", response_model=JiraDryRunResponse)
    def jira_dry_run(payload: JiraDryRunRequest) -> JiraDryRunResponse:
        try:
            return dry_run_plan_handoff(
                payload.project_key,
                payload.plan,
                engineers=_resolve_payload_engineers(payload),
                team_capacity=_resolve_payload_team_capacity(payload),
                accept_warnings=payload.accept_warnings,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except JiraError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/v1/jira/handoff", response_model=JiraHandoffResult)
    def jira_handoff(payload: JiraHandoffRequest) -> JiraHandoffResult:
        try:
            return create_plan_epic(
                payload.project_key,
                payload.plan,
                engineers=_resolve_payload_engineers(payload),
                team_capacity=_resolve_payload_team_capacity(payload),
                accept_warnings=payload.accept_warnings,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except JiraError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


app = create_app()


def _resolve_payload_engineers(payload: SprintPlanActionRequest | JiraDryRunRequest) -> list[EmployeeRecord]:
    return payload.engineer_profiles or payload.plan.engineer_profiles


def _resolve_payload_team_capacity(payload: SprintPlanActionRequest | JiraDryRunRequest):
    return payload.team_capacity if payload.team_capacity is not None else payload.plan.team_capacity
