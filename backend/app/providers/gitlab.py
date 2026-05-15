from __future__ import annotations

import hmac

from app.providers.base import GitProvider, SignatureError, WebhookEvent

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
