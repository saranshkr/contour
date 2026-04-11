from __future__ import annotations

from typing import Any

from contour.jira_client import JiraClient
from contour.services.field_meta import FieldMetadataService


class EpicCreationHandler:
    def __init__(self, jira_client: JiraClient, field_service: FieldMetadataService):
        self.jira_client = jira_client
        self.field_service = field_service

    @staticmethod
    def _canonical(name: str) -> str:
        return name.lower().replace(" ", "")

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

            if meta["required"] and canonical_name not in {"project", "worktype", "reporter"}:
                raise ValueError(f"Required field '{human_name}' missing from Jira payload")

        if "summary" not in mapped:
            summary = lookup.get("summary")
            if not summary:
                raise ValueError("'summary' missing from Jira payload")
            mapped["summary"] = summary

        if "description" not in mapped:
            description = lookup.get("description")
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
        data = {
            "fields": {
                **epic_payload,
                "project": {"key": project_key},
                "issuetype": {"name": "Epic"},
            }
        }
        result = self.jira_client.post("/rest/api/2/issue", payload=data)
        return result.get("key")
