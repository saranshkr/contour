from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from contour.models import JiraSyncState


class JiraSyncStore:
    def __init__(self, database_path: str | Path | None = None):
        default_path = Path(__file__).resolve().parents[3] / "artifacts" / "jira_sync_state.db"
        self.database_path = Path(database_path or default_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def get(self, idempotency_key: str) -> JiraSyncState | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT project_key, status, epic_key, child_issue_keys, validation_errors,
                       validation_warnings, last_error
                FROM jira_sync_state
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return JiraSyncState(
            idempotency_key=idempotency_key,
            project_key=row[0],
            status=row[1],
            epic_key=row[2],
            child_issue_keys=json.loads(row[3] or "{}"),
            validation_errors=json.loads(row[4] or "[]"),
            validation_warnings=json.loads(row[5] or "[]"),
            last_error=row[6],
        )

    def save(self, state: JiraSyncState) -> JiraSyncState:
        payload = (
            state.idempotency_key,
            state.project_key,
            state.status.value,
            state.epic_key,
            json.dumps(state.child_issue_keys),
            json.dumps([item.model_dump() for item in state.validation_errors]),
            json.dumps([item.model_dump() for item in state.validation_warnings]),
            state.last_error,
        )
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO jira_sync_state (
                    idempotency_key, project_key, status, epic_key, child_issue_keys,
                    validation_errors, validation_warnings, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    project_key = excluded.project_key,
                    status = excluded.status,
                    epic_key = excluded.epic_key,
                    child_issue_keys = excluded.child_issue_keys,
                    validation_errors = excluded.validation_errors,
                    validation_warnings = excluded.validation_warnings,
                    last_error = excluded.last_error
                """,
                payload,
            )
            connection.commit()
        return state

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jira_sync_state (
                    idempotency_key TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    epic_key TEXT,
                    child_issue_keys TEXT NOT NULL,
                    validation_errors TEXT NOT NULL,
                    validation_warnings TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )
            connection.commit()
