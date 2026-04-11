from __future__ import annotations

import json

from contour.models import SprintRequest

DEFAULT_SPRINT_NAME = "Sprint 18"
DEFAULT_GOAL = "Ship a reliable Contour MVP planning and Jira handoff workflow."

DEFAULT_BACKLOG_ITEMS = [
    {
        "id": "CTR-101",
        "title": "Build Contour planning workspace",
        "description": "Create a web experience for sprint goal, backlog items, and team roster entry.",
        "priority": "High",
        "dependencies": [],
        "owner_hint": "Avery",
        "labels": ["frontend", "web-ui"],
    },
    {
        "id": "CTR-102",
        "title": "Generate sprint recommendations",
        "description": "Use the planning pipeline to recommend selected work, owners, and rationales for the next sprint.",
        "priority": "High",
        "dependencies": ["CTR-101"],
        "owner_hint": "Jordan",
        "labels": ["backend", "ai"],
    },
    {
        "id": "CTR-103",
        "title": "Create Jira handoff epic",
        "description": "Convert an approved sprint plan into a single Jira epic with selected work, risks, and capacity summary.",
        "priority": "Medium",
        "dependencies": ["CTR-102"],
        "owner_hint": "Riley",
        "labels": ["jira", "integration"],
    },
]

DEFAULT_TEAM_MEMBERS = [
    {
        "name": "Avery",
        "role": "Frontend Engineer",
        "skills": ["frontend", "react", "ui"],
        "capacity_points": 8,
    },
    {
        "name": "Jordan",
        "role": "Backend Engineer",
        "skills": ["backend", "ai", "python"],
        "capacity_points": 10,
    },
    {
        "name": "Riley",
        "role": "Platform Engineer",
        "skills": ["jira", "integration", "python"],
        "capacity_points": 6,
    },
]


def backlog_seed_json() -> str:
    return json.dumps(DEFAULT_BACKLOG_ITEMS, indent=2)


def team_seed_json() -> str:
    return json.dumps(DEFAULT_TEAM_MEMBERS, indent=2)


def build_sample_request() -> SprintRequest:
    return SprintRequest(
        sprint_name=DEFAULT_SPRINT_NAME,
        goal=DEFAULT_GOAL,
        backlog_items=DEFAULT_BACKLOG_ITEMS,
        team_members=DEFAULT_TEAM_MEMBERS,
    )
