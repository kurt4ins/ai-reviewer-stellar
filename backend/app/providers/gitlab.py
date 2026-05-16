from __future__ import annotations

import base64
import hmac
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.providers.base import (
    ChangedFile,
    CodeSearchHit,
    GitProvider,
    PostedComment,
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

    @staticmethod
    async def get_file_content(
        token: str,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        settings = get_settings()
        headers = {"PRIVATE-TOKEN": token}
        project_id = quote(f"{owner}/{repo}", safe="")
        file_path = quote(path, safe="")
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.gitlab_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            resp = await client.get(
                f"/projects/{project_id}/repository/files/{file_path}",
                params={"ref": ref},
                headers=headers,
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"gitlab files api {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            content_b64 = data.get("content")
            if not content_b64:
                raise ProviderAPIError(f"gitlab files: missing content at {path}")
            try:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
            except (ValueError, TypeError) as exc:
                raise ProviderAPIError(f"gitlab files decode: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    async def search_code(
        token: str,
        owner: str,
        repo: str,
        query: str,
        *,
        limit: int = 5,
        client: httpx.AsyncClient | None = None,
    ) -> list[CodeSearchHit]:
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
                f"/projects/{project_id}/search",
                params={"scope": "blobs", "search": query, "per_page": limit},
                headers=headers,
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"gitlab search api {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            hits: list[CodeSearchHit] = []
            for item in data[:limit]:
                hits.append(
                    CodeSearchHit(
                        path=item.get("path") or item.get("filename") or "",
                        snippet=str(item.get("data", "")),
                    )
                )
            return hits
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    async def post_review_comment(
        token: str,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        path: str,
        line: int,
        body: str,
        client: httpx.AsyncClient | None = None,
    ) -> PostedComment:
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
            mr_resp = await client.get(
                f"/projects/{project_id}/merge_requests/{pr_number}",
                headers=headers,
            )
            if mr_resp.status_code >= 400:
                raise ProviderAPIError(
                    f"gitlab mr fetch {mr_resp.status_code}: {mr_resp.text[:200]}"
                )
            diff_refs = (mr_resp.json() or {}).get("diff_refs") or {}
            base_sha = diff_refs.get("base_sha")
            start_sha = diff_refs.get("start_sha")
            head_sha = diff_refs.get("head_sha") or commit_sha
            if not (base_sha and start_sha and head_sha):
                raise ProviderAPIError("gitlab mr: incomplete diff_refs")

            resp = await client.post(
                f"/projects/{project_id}/merge_requests/{pr_number}/discussions",
                headers=headers,
                json={
                    "body": body,
                    "position": {
                        "position_type": "text",
                        "base_sha": base_sha,
                        "start_sha": start_sha,
                        "head_sha": head_sha,
                        "new_path": path,
                        "new_line": line,
                    },
                },
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"gitlab discussion {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            discussion_id = data.get("id")
            if discussion_id is None:
                raise ProviderAPIError("gitlab discussion: missing id in response")
            return PostedComment(provider_comment_id=str(discussion_id))
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    async def set_commit_status(
        token: str,
        owner: str,
        repo: str,
        commit_sha: str,
        state: str,
        description: str,
        *,
        context: str = "security/ai-review",
        target_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        headers = {"PRIVATE-TOKEN": token}
        project_id = quote(f"{owner}/{repo}", safe="")
        gl_state = {"failure": "failed"}.get(state, state)
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.gitlab_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            params = {
                "state": gl_state,
                "name": context,
                "description": description[:255],
            }
            if target_url:
                params["target_url"] = target_url
            resp = await client.post(
                f"/projects/{project_id}/statuses/{commit_sha}",
                headers=headers,
                params=params,
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"gitlab commit status {resp.status_code}: {resp.text[:200]}"
                )
        finally:
            if owns_client:
                await client.aclose()
