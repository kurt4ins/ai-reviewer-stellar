from __future__ import annotations

import hashlib
import hmac

from app.providers.base import GitProvider, SignatureError, WebhookEvent

SUPPORTED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


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
