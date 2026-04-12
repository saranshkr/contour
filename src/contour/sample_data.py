from __future__ import annotations

import json

from contour.models import EmployeeRecord, SprintRequest

DEFAULT_SPRINT_NAME = "Sprint 18"
DEFAULT_GOAL = "Ship a reliable Contour MVP planning and Jira handoff workflow."

DEFAULT_TASKS = [
    {
        "text": "Build the Contour planning workspace so PMs can enter a sprint goal and a freeform list of tasks, then review the generated Jira-ready draft before approval.",
        "owner_hint": "Avery",
    },
    {
        "text": "Implement the backend planning pipeline that normalizes task descriptions, estimates story points, and recommends Jira ticket types and assignees based on team skills.",
        "owner_hint": "Jordan",
    },
    {
        "text": "Create the Jira handoff flow that generates one epic plus child stories or tasks, writes story points when the field exists, and leaves overflow work unassigned.",
        "owner_hint": "Riley",
    },
]

DEFAULT_EMPLOYEES = [
    {
        "id": "emp-avery",
        "name": "Avery",
        "role": "Frontend Engineer",
        "skills": ["frontend", "react", "ui", "next.js"],
        "capacity_points": 8,
        "jira_account_id": "acct-avery",
    },
    {
        "id": "emp-jordan",
        "name": "Jordan",
        "role": "Backend Engineer",
        "skills": ["backend", "ai", "python", "api"],
        "capacity_points": 10,
        "jira_account_id": "acct-jordan",
    },
    {
        "id": "emp-riley",
        "name": "Riley",
        "role": "Platform Engineer",
        "skills": ["jira", "integration", "python", "automation"],
        "capacity_points": 6,
        "jira_account_id": "acct-riley",
    },
]


def task_seed_json() -> str:
    return json.dumps(DEFAULT_TASKS, indent=2)


def employee_seed_json() -> str:
    return json.dumps(DEFAULT_EMPLOYEES, indent=2)


def build_sample_request() -> SprintRequest:
    return SprintRequest(
        sprint_name=DEFAULT_SPRINT_NAME,
        goal=DEFAULT_GOAL,
        tasks=DEFAULT_TASKS,
    )


def build_employee_roster() -> list[EmployeeRecord]:
    return [EmployeeRecord.model_validate(employee) for employee in DEFAULT_EMPLOYEES]
