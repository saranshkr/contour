from __future__ import annotations

import re
from typing import Any

from contour.jira_client import JiraClient


class FieldMetadataService:
    def __init__(self, jira_client: JiraClient):
        self.jira_client = jira_client

    def get_epic_fields(self, project_key: str) -> dict[str, Any]:
        return self.get_issue_type_fields(project_key, "Epic")

    def get_issue_type_fields(self, project_key: str, issue_type_name: str) -> dict[str, Any]:
        issue_types = self.jira_client.get(
            f"/rest/api/3/issue/createmeta/{project_key}/issuetypes"
        )["issueTypes"]
        issue_type_id = next(
            issue_type["id"]
            for issue_type in issue_types
            if issue_type["name"].lower() == issue_type_name.lower()
        )

        issue_meta = self.jira_client.get(
            f"/rest/api/3/issue/createmeta/{project_key}/issuetypes/{issue_type_id}"
        )
        all_fields = self.jira_client.get("/rest/api/3/field")
        return self._process_field_metadata(all_fields, [issue_meta])

    def get_user_id(self) -> str:
        return self.jira_client.get("/rest/api/3/myself")["accountId"]

    def find_story_points_field(self, field_requirements: dict[str, Any]) -> str | None:
        for display_name, meta in field_requirements.items():
            canonical_name = self._canonical(display_name)
            if canonical_name in {"storypoints", "storypointestimate", "storypoint"}:
                return meta["id"]
        return None

    def find_epic_link_field(self, field_requirements: dict[str, Any]) -> dict[str, str] | None:
        for display_name, meta in field_requirements.items():
            canonical_name = self._canonical(display_name)
            if canonical_name == "parent" or meta["id"] == "parent":
                return {"mode": "parent", "field_id": meta["id"]}
            if canonical_name in {"epiclink", "epiclinkrelationship"}:
                return {"mode": "epic_link", "field_id": meta["id"]}
        return None

    def _process_field_metadata(
        self,
        all_fields: list[dict[str, Any]],
        issue_type_payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        id_index = {field["id"]: field for field in all_fields}
        issue_fields: dict[str, Any] = {}

        for issue_type in issue_type_payloads:
            raw_fields = issue_type.get("fields") or {}
            if isinstance(raw_fields, dict):
                field_items = raw_fields.items()
            else:
                field_items = ((field["fieldId"], field) for field in raw_fields)

            for field_id, field_meta in field_items:
                full_meta = id_index.get(field_id, {})
                display_name = field_meta.get("name") or full_meta.get("name") or field_id
                issue_fields[display_name] = {
                    "id": field_id,
                    "required": field_meta.get("required", False),
                    "schema": field_meta.get("schema", full_meta.get("schema", {})),
                    "allowed": field_meta.get(
                        "allowedValues",
                        full_meta.get("allowedValues"),
                    ),
                }

        return issue_fields

    @staticmethod
    def _canonical(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.strip().lower())
