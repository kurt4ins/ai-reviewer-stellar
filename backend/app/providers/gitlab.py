from __future__ import annotations

import hmac
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.providers.base import (
    ChangedFile,
    GitProvider,
    ProviderAPIError,
    SignatureError,
    WebhookEvent,
)

SUPPORTED_ACTIONS = {"open", "reopen", "update"}


class GitLabProvider(GitProvider):
    name = "gitlab"

    @staticmethod
    def verify_signature(secret: str, raw_body: bytes, headers: dict[str, str]) -> None:
        token = headers.get("x-gitlab-token") or headers.get("X-Gitlab-Token")
        if not token:
            raise SignatureError("missing X-Gitlab-Token header")
        if not hmac.compare_digest(token, secret):
            raise SignatureError("token mismatch")

    @staticmethod
    def parse_event(headers: dict[str, str], payload: dict) -> WebhookEvent | None:
        event_type = (
            headers.get("x-gitlab-event")
            or headers.get("X-Gitlab-Event")
            or payload.get("object_kind", "")
        )
        if event_type not in {"Merge Request Hook", "merge_request"}:
            return None

        attrs = payload.get("object_attributes") or {}
        action = attrs.get("action")
        if action not in SUPPORTED_ACTIONS:
            return None

        project = payload.get("project") or {}
        path_with_namespace = project.get("path_with_namespace")
        if not path_with_namespace or "/" not in path_with_namespace:
            return None
        owner, name = path_with_namespace.rsplit("/", 1)

        pr_number = attrs.get("iid")
        commit_sha = (attrs.get("last_commit") or {}).get("id") or attrs.get("last_commit_sha")
        if pr_number is None or not commit_sha:
            return None

        return WebhookEvent(
            provider="gitlab",
            event_type="merge_request",
            action=str(action),
            owner=owner,
            repo=name,
            pr_number=int(pr_number),
            commit_sha=str(commit_sha),
        )

    @staticmethod
    def _file_status(change: dict) -> str:
        if change.get("new_file"):
            return "added"
        if change.get("deleted_file"):
            return "removed"
        if change.get("renamed_file"):
            return "renamed"
        return "modified"

    @staticmethod
    async def get_pr_diff(
        token: str,
        owner: str,
        repo: str,
        pr_number: int,
        client: httpx.AsyncClient | None = None,
    ) -> list[ChangedFile]:
        settings = get_settings()
        headers = {"PRIVATE-TOKEN": token}
        project_id = quote(f"{owner}/{repo}", safe="")
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.gitlab_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            resp = await client.get(
                f"/projects/{project_id}/merge_requests/{pr_number}/changes",
                headers=headers,
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"gitlab changes api {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            files: list[ChangedFile] = []
            for change in data.get("changes", []):
                diff = change.get("diff") or ""
                files.append(
                    ChangedFile(
                        path=change.get("new_path") or change.get("old_path"),
                        old_path=change.get("old_path"),
                        status=GitLabProvider._file_status(change),
                        patch=diff or None,
                    )
                )
            return files
        finally:
            if owns_client:
                await client.aclose()
