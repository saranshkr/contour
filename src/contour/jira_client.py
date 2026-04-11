from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import find_dotenv, load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

load_dotenv(find_dotenv() or Path(__file__).resolve().parents[2] / ".env")


class JiraError(RuntimeError):
    pass


class JiraClient:
    """Thin wrapper around the Jira Cloud REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        self.base_url = (base_url or os.environ["JIRA_BASE_URL"]).rstrip("/")
        email = email or os.environ["JIRA_EMAIL"]
        api_token = api_token or os.environ["JIRA_API_TOKEN"]

        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(JiraError),
    )
    def get(self, path: str, **params: Any) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.get(url, params=params)
        if not response.ok:
            raise JiraError(f"GET {url} -> {response.status_code}: {response.text}")
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(JiraError),
    )
    def post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.post(url, data=json.dumps(payload))
        if not response.ok:
            raise JiraError(f"POST {url} -> {response.status_code}: {response.text}")
        return response.json()
