from __future__ import annotations

import re
from typing import Any

from contour.jira_client import JiraClient
from contour.services.field_meta import FieldMetadataService


class EpicCreationHandler:
    def __init__(self, jira_client: JiraClient, field_service: FieldMetadataService):
        self.jira_client = jira_client
        self.field_service = field_service

    def map_fields(
        self,
        draft_fields: dict[str, Any],
        field_requirements: dict[str, Any],
        account_id: str,
    ) -> dict[str, Any]:
        lookup = {self._canonical(key): value for key, value in draft_fields.items()}
        mapped: dict[str, Any] = {}

        for human_name, meta in field_requirements.items():
            field_id = meta["id"]
            canonical_name = self._canonical(human_name)

            if field_id in draft_fields:
                mapped[field_id] = draft_fields[field_id]
                continue

            if canonical_name in lookup:
                mapped[field_id] = lookup[canonical_name]
                continue

            if canonical_name == "epicname" and "summary" in lookup:
                mapped[field_id] = lookup["summary"]
                continue

            if meta["required"] and canonical_name not in {"project", "issuetype", "reporter"}:
                raise ValueError(f"Required field '{human_name}' missing from Jira payload")

        if "summary" not in mapped:
            summary = draft_fields.get("summary") or lookup.get("summary")
            if not summary:
                raise ValueError("'summary' missing from Jira payload")
            mapped["summary"] = summary

        if "description" not in mapped:
            description = draft_fields.get("description") or lookup.get("description")
            if not description:
                raise ValueError("'description' missing from Jira payload")
            mapped["description"] = description

        labels = draft_fields.get("labels") or lookup.get("labels")
        if labels:
            mapped["labels"] = labels

        priority = draft_fields.get("priority") or lookup.get("priority")
        if priority:
            mapped["priority"] = priority if isinstance(priority, dict) else {"name": priority}

        mapped["reporter"] = {"id": account_id}
        return mapped

    def create_epic(self, project_key: str, epic_payload: dict[str, Any]) -> str:
        return self.create_issue(project_key, "Epic", epic_payload)

    def create_issue(
        self,
        project_key: str,
        issue_type_name: str,
        issue_payload: dict[str, Any],
    ) -> str:
        data = {
            "fields": {
                **issue_payload,
                "project": {"key": project_key},
                "issuetype": {"name": issue_type_name},
            }
        }
        result = self.jira_client.post("/rest/api/2/issue", payload=data)
        return result.get("key")

    @staticmethod
    def _canonical(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", name.lower())
