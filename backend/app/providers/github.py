from __future__ import annotations

import base64
import hashlib
import hmac

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

SUPPORTED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}

_PER_PAGE = 100
_STATUS_MAP = {
    "added": "added",
    "modified": "modified",
    "removed": "removed",
    "renamed": "renamed",
    "changed": "modified",
    "copied": "added",
}


class GitHubProvider(GitProvider):
    name = "github"

    @staticmethod
    def verify_signature(secret: str, raw_body: bytes, headers: dict[str, str]) -> None:
        header_value = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        if not header_value:
            raise SignatureError("missing X-Hub-Signature-256 header")
        if not header_value.startswith("sha256="):
            raise SignatureError("malformed signature header")
        provided = header_value.split("=", 1)[1].strip()
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            raise SignatureError("signature mismatch")

    @staticmethod
    def parse_event(headers: dict[str, str], payload: dict) -> WebhookEvent | None:
        event_type = headers.get("x-github-event") or headers.get("X-GitHub-Event")
        if not event_type:
            return None
        if event_type == "ping":
            return None
        if event_type != "pull_request":
            return None

        action = payload.get("action")
        if action not in SUPPORTED_ACTIONS:
            return None

        pull_request = payload.get("pull_request") or {}
        repo = payload.get("repository") or {}
        head = pull_request.get("head") or {}

        full_name = repo.get("full_name")
        if not full_name or "/" not in full_name:
            return None
        owner, name = full_name.split("/", 1)

        pr_number = pull_request.get("number")
        commit_sha = head.get("sha")
        if pr_number is None or not commit_sha:
            return None

        return WebhookEvent(
            provider="github",
            event_type=event_type,
            action=action,
            owner=owner,
            repo=name,
            pr_number=int(pr_number),
            commit_sha=str(commit_sha),
        )

    @staticmethod
    async def get_pr_diff(
        token: str,
        owner: str,
        repo: str,
        pr_number: int,
        client: httpx.AsyncClient | None = None,
    ) -> list[ChangedFile]:
        settings = get_settings()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.github_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            files: list[ChangedFile] = []
            page = 1
            while True:
                resp = await client.get(
                    f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                    params={"per_page": _PER_PAGE, "page": page},
                    headers=headers,
                )
                if resp.status_code >= 400:
                    raise ProviderAPIError(
                        f"github files api {resp.status_code}: {resp.text[:200]}"
                    )
                batch = resp.json()
                for item in batch:
                    raw_status = item.get("status", "modified")
                    files.append(
                        ChangedFile(
                            path=item["filename"],
                            old_path=item.get("previous_filename"),
                            status=_STATUS_MAP.get(raw_status, "modified"),
                            patch=item.get("patch"),
                        )
                    )
                if len(batch) < _PER_PAGE:
                    break
                page += 1
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.github_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            resp = await client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": ref},
                headers=headers,
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"github contents api {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            if data.get("type") != "file" or "content" not in data:
                raise ProviderAPIError(f"github contents: not a file at {path}")
            encoding = data.get("encoding", "base64")
            if encoding != "base64":
                raise ProviderAPIError(f"github contents: unexpected encoding {encoding}")
            try:
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except (ValueError, TypeError) as exc:
                raise ProviderAPIError(f"github contents decode: {exc}") from exc
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.text-match+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.github_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            resp = await client.get(
                "/search/code",
                params={
                    "q": f"{query} repo:{owner}/{repo}",
                    "per_page": limit,
                },
                headers=headers,
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"github search api {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            hits: list[CodeSearchHit] = []
            for item in data.get("items", [])[:limit]:
                snippet_parts = [
                    str(m.get("fragment", ""))
                    for m in (item.get("text_matches") or [])
                ]
                snippet = "\n---\n".join(p for p in snippet_parts if p)
                hits.append(CodeSearchHit(path=item.get("path", ""), snippet=snippet))
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=settings.github_api_url,
                headers=headers,
                timeout=settings.git_http_timeout,
            )
        try:
            resp = await client.post(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                headers=headers,
                json={
                    "body": body,
                    "commit_id": commit_sha,
                    "path": path,
                    "line": line,
                    "side": "RIGHT",
                },
            )
            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"github review comment {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            comment_id = data.get("id")
            if comment_id is None:
                raise ProviderAPIError("github review comment: missing id in response")
            return PostedComment(provider_comment_id=str(comment_id))
        finally:
            if owns_client:
                await client.aclose()
