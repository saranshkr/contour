from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from contour.jira_client import JiraError
from contour.models import SprintPlan, SprintRequest
from contour.orchestrator import approve_plan, create_plan_epic, plan_sprint
from contour.sample_data import build_sample_request


def _allowed_origins() -> list[str]:
    configured = os.getenv("CONTOUR_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


class JiraHandoffRequest(BaseModel):
    project_key: str = Field(min_length=1)
    approved_plan: SprintPlan


class JiraHandoffResponse(BaseModel):
    key: str
    url: str | None = None


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

    @app.post("/api/v1/plans/generate", response_model=SprintPlan)
    def generate_plan(request: SprintRequest) -> SprintPlan:
        return plan_sprint(request)

    @app.post("/api/v1/plans/approve", response_model=SprintPlan)
    def approve_draft(plan: SprintPlan) -> SprintPlan:
        return approve_plan(plan)

    @app.post("/api/v1/jira/handoff", response_model=JiraHandoffResponse)
    def jira_handoff(payload: JiraHandoffRequest) -> JiraHandoffResponse:
        try:
            key = create_plan_epic(payload.project_key, payload.approved_plan)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except JiraError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        url = f"{base_url}/browse/{key}" if base_url else None
        return JiraHandoffResponse(key=key, url=url)

    return app


app = create_app()
