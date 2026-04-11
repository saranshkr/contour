from __future__ import annotations

import json
import os

import streamlit as st
from dotenv import find_dotenv, load_dotenv
from pydantic import ValidationError

from contour.models import SprintPlan, SprintRequest
from contour.orchestrator import approve_plan, create_plan_epic, plan_sprint
from contour.sample_data import (
    DEFAULT_GOAL,
    DEFAULT_SPRINT_NAME,
    backlog_seed_json,
    team_seed_json,
)

load_dotenv(find_dotenv())


def _build_request(
    sprint_name: str,
    goal: str,
    backlog_text: str,
    team_text: str,
) -> SprintRequest:
    backlog_items = json.loads(backlog_text)
    team_members = json.loads(team_text)
    return SprintRequest(
        sprint_name=sprint_name,
        goal=goal,
        backlog_items=backlog_items,
        team_members=team_members,
    )


def _render_plan(plan: SprintPlan) -> None:
    if plan.approval_state == "approved":
        st.success("Approval state: approved")
    else:
        st.info("Approval state: draft")

    capacity = plan.capacity_summary
    metric_columns = st.columns(3)
    metric_columns[0].metric("Selected Points", capacity.selected_points)
    metric_columns[1].metric("Total Capacity", capacity.total_capacity_points)
    metric_columns[2].metric("Remaining Capacity", capacity.remaining_points)

    st.subheader("Selected Sprint Items")
    if not plan.selected_items:
        st.warning("No sprint items were selected.")
    for item in plan.selected_items:
        with st.expander(f"{item.id} · {item.title} · {item.estimated_points} pts", expanded=True):
            st.markdown(f"**Assignee:** {item.recommended_assignee}")
            if item.alternative_assignees:
                st.markdown(f"**Alternatives:** {', '.join(item.alternative_assignees)}")
            st.markdown(f"**Why it was selected:** {item.selection_rationale}")
            st.markdown(f"**Why this owner:** {item.assignment_rationale}")
            if item.required_skills:
                st.markdown(f"**Required skills:** {', '.join(item.required_skills)}")
            if item.ambiguity_flags:
                st.markdown(f"**Ambiguity flags:** {', '.join(item.ambiguity_flags)}")
            if item.dependency_signals:
                st.markdown(f"**Dependencies:** {', '.join(item.dependency_signals)}")

    st.subheader("Deferred Items")
    if plan.deferred_items:
        for item in plan.deferred_items:
            st.markdown(f"- `{item.id}` {item.title} ({item.estimated_points} pts)")
    else:
        st.markdown("- None")

    st.subheader("Capacity by Team Member")
    capacity_rows = [
        {
            "Member": allocation.member_name,
            "Assigned": allocation.assigned_points,
            "Capacity": allocation.capacity_points,
            "Remaining": allocation.remaining_points,
        }
        for allocation in capacity.allocations
    ]
    st.dataframe(capacity_rows, hide_index=True, use_container_width=True)

    st.subheader("Risk Review")
    if not plan.risks:
        st.success("No major planning risks were flagged.")
    for risk in plan.risks:
        st.markdown(
            f"- **{risk.severity.upper()} · {risk.category}**: {risk.message} "
            f"Suggested action: {risk.suggested_action}"
        )


st.set_page_config(page_title="Contour", page_icon="🧭", layout="wide")
st.title("Contour")
st.caption("Contour helps you plan a sprint, review recommendations, approve the draft, and hand off one final plan epic to Jira.")

if "backlog_text" not in st.session_state:
    st.session_state["backlog_text"] = backlog_seed_json()
if "team_text" not in st.session_state:
    st.session_state["team_text"] = team_seed_json()

with st.sidebar:
    st.header("Jira Handoff")
    project_key = st.text_input("Jira Project Key", "CTR")
    st.caption("The Jira handoff button stays disabled until the draft is approved.")

st.subheader("1. Intake")
with st.form("sprint_input_form", clear_on_submit=False):
    sprint_name = st.text_input("Sprint Name", value=st.session_state.get("sprint_name", DEFAULT_SPRINT_NAME))
    goal = st.text_area("Sprint Goal", value=st.session_state.get("goal", DEFAULT_GOAL), height=80)
    backlog_text = st.text_area(
        "Backlog Items (JSON array)",
        value=st.session_state["backlog_text"],
        height=280,
    )
    team_text = st.text_area(
        "Team Roster (JSON array)",
        value=st.session_state["team_text"],
        height=220,
    )
    generate = st.form_submit_button("Generate Sprint Plan")

if generate:
    st.session_state["sprint_name"] = sprint_name
    st.session_state["goal"] = goal
    st.session_state["backlog_text"] = backlog_text
    st.session_state["team_text"] = team_text
    try:
        request = _build_request(sprint_name, goal, backlog_text, team_text)
        plan = plan_sprint(request)
        st.session_state["request"] = request
        st.session_state["plan"] = plan
        st.success("Draft sprint plan generated. Review the recommendation below.")
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON input: {exc}")
    except ValidationError as exc:
        st.error(f"Input validation failed: {exc}")
    except Exception as exc:  # pragma: no cover - runtime safety for app use
        st.error(f"Plan generation failed: {exc}")

if "plan" in st.session_state:
    plan: SprintPlan = st.session_state["plan"]

    st.subheader("2. Draft Review")
    _render_plan(plan)

    st.subheader("3. Approval")
    approval_cols = st.columns(2)
    with approval_cols[0]:
        if st.button("Regenerate Draft"):
            try:
                refreshed_plan = plan_sprint(st.session_state["request"])
                st.session_state["plan"] = refreshed_plan
                st.success("Draft regenerated.")
                st.rerun()
            except Exception as exc:  # pragma: no cover - runtime safety for app use
                st.error(f"Could not regenerate plan: {exc}")
    with approval_cols[1]:
        if plan.approval_state == "draft":
            if st.button("Approve Plan"):
                st.session_state["plan"] = approve_plan(plan)
                st.success("Plan approved and ready for Jira handoff.")
                st.rerun()
        else:
            st.success("This sprint plan has already been approved.")

    st.subheader("4. Jira Handoff")
    create_disabled = plan.approval_state != "approved"
    if st.button("Create Jira Plan Epic", disabled=create_disabled):
        try:
            key = create_plan_epic(project_key, st.session_state["plan"])
            base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
            st.success(f"Created Jira epic {key}.")
            if base_url:
                st.markdown(f"[Open in Jira]({base_url}/browse/{key})")
        except Exception as exc:  # pragma: no cover - runtime safety for app use
            st.error(f"Jira handoff failed: {exc}")
