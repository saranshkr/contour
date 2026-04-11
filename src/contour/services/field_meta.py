from __future__ import annotations

from typing import Any

from contour.jira_client import JiraClient


class FieldMetadataService:
    def __init__(self, jira_client: JiraClient):
        self.jira_client = jira_client

    def get_epic_fields(self, project_key: str) -> dict[str, Any]:
        issue_types = self.jira_client.get(
            f"/rest/api/3/issue/createmeta/{project_key}/issuetypes"
        )["issueTypes"]
        epic_id = next(
            issue_type["id"]
            for issue_type in issue_types
            if issue_type["name"].lower() == "epic"
        )

        epic_meta = self.jira_client.get(
            f"/rest/api/3/issue/createmeta/{project_key}/issuetypes/{epic_id}"
        )
        all_fields = self.jira_client.get("/rest/api/3/field")
        return self._process_field_metadata(all_fields, [epic_meta])

    def get_user_id(self) -> str:
        return self.jira_client.get("/rest/api/3/myself")["accountId"]

    def _process_field_metadata(
        self,
        all_fields: list[dict[str, Any]],
        issue_type_payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        id_index = {field["id"]: field for field in all_fields}
        epic_fields: dict[str, Any] = {}

        for issue_type in issue_type_payloads:
            raw_fields = issue_type.get("fields") or {}
            if isinstance(raw_fields, dict):
                field_items = raw_fields.items()
            else:
                field_items = ((field["fieldId"], field) for field in raw_fields)

            for field_id, field_meta in field_items:
                full_meta = id_index.get(field_id, {})
                display_name = field_meta.get("name") or full_meta.get("name") or field_id
                epic_fields[display_name] = {
                    "id": field_id,
                    "required": field_meta.get("required", False),
                    "schema": field_meta.get("schema", full_meta.get("schema", {})),
                    "allowed": field_meta.get(
                        "allowedValues",
                        full_meta.get("allowedValues"),
                    ),
                }

        return epic_fields
