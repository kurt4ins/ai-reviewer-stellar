from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import webhooks
from app.db import repositories as repo_module
from app.db.session import get_db


@dataclass
class FakeRepo:
    id: uuid.UUID
    provider: str
    owner: str
    name: str
    webhook_secret: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class FakeArq:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def enqueue_job(self, name: str, *args: Any, **kwargs: Any):
        self.jobs.append((name, args, kwargs))

        class _Job:
            job_id = kwargs.get("_job_id", "fake-job-id")

        return _Job()


@pytest.fixture
def fake_repo() -> FakeRepo:
    return FakeRepo(
        id=uuid.uuid4(),
        provider="github",
        owner="acme",
        name="widgets",
        webhook_secret="topsecret",
    )


@pytest.fixture
def app_and_arq(monkeypatch: pytest.MonkeyPatch, fake_repo: FakeRepo):
    async def fake_get_repository(_session, provider, owner, name):
        if (provider, owner, name) == (fake_repo.provider, fake_repo.owner, fake_repo.name):
            return fake_repo
        return None

    monkeypatch.setattr(repo_module, "get_repository", fake_get_repository)
    monkeypatch.setattr(webhooks, "get_repository", fake_get_repository)

    async def override_db():
        yield None

    arq = FakeArq()

    app = FastAPI()
    app.include_router(webhooks.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[webhooks._get_arq] = lambda: arq

    return app, arq


def _gh_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_webhook_enqueues_job(app_and_arq, fake_repo: FakeRepo):
    app, arq = app_and_arq
    client = TestClient(app)

    payload = {
        "action": "opened",
        "pull_request": {"number": 1, "head": {"sha": "abcdef"}},
        "repository": {"full_name": f"{fake_repo.owner}/{fake_repo.name}"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-github-event": "pull_request",
        "x-hub-signature-256": _gh_sig(fake_repo.webhook_secret, body),
        "content-type": "application/json",
    }

    response = client.post("/webhook/github", content=body, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["pr_number"] == 1
    assert data["commit_sha"] == "abcdef"
    assert data["provider"] == "github"
    assert len(arq.jobs) == 1
    name, args, _ = arq.jobs[0]
    assert name == "review_pull_request"
    assert args[0] == "github"
    assert args[2] == 1
    assert args[3] == "abcdef"


def test_github_webhook_rejects_bad_signature(app_and_arq, fake_repo: FakeRepo):
    app, arq = app_and_arq
    client = TestClient(app)

    payload = {
        "action": "opened",
        "pull_request": {"number": 1, "head": {"sha": "abcdef"}},
        "repository": {"full_name": f"{fake_repo.owner}/{fake_repo.name}"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-github-event": "pull_request",
        "x-hub-signature-256": _gh_sig("wrong-secret", body),
        "content-type": "application/json",
    }

    response = client.post("/webhook/github", content=body, headers=headers)

    assert response.status_code == 401
    assert arq.jobs == []


def test_github_webhook_unknown_repo_returns_404(app_and_arq, fake_repo: FakeRepo):
    app, arq = app_and_arq
    client = TestClient(app)

    payload = {
        "action": "opened",
        "pull_request": {"number": 1, "head": {"sha": "x"}},
        "repository": {"full_name": "other/repo"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-github-event": "pull_request",
        "x-hub-signature-256": _gh_sig(fake_repo.webhook_secret, body),
        "content-type": "application/json",
    }

    response = client.post("/webhook/github", content=body, headers=headers)

    assert response.status_code == 404
    assert arq.jobs == []


def test_github_webhook_ignores_ping(app_and_arq, fake_repo: FakeRepo):
    app, arq = app_and_arq
    client = TestClient(app)

    body = b"{}"
    headers = {
        "x-github-event": "ping",
        "x-hub-signature-256": _gh_sig(fake_repo.webhook_secret, body),
        "content-type": "application/json",
    }

    response = client.post("/webhook/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert arq.jobs == []


def test_github_webhook_ignores_closed_action(app_and_arq, fake_repo: FakeRepo):
    app, arq = app_and_arq
    client = TestClient(app)

    payload = {
        "action": "closed",
        "pull_request": {"number": 1, "head": {"sha": "x"}},
        "repository": {"full_name": f"{fake_repo.owner}/{fake_repo.name}"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-github-event": "pull_request",
        "x-hub-signature-256": _gh_sig(fake_repo.webhook_secret, body),
        "content-type": "application/json",
    }

    response = client.post("/webhook/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert arq.jobs == []


def test_gitlab_webhook_enqueues_job(monkeypatch: pytest.MonkeyPatch, fake_repo: FakeRepo):
    fake_repo = FakeRepo(
        id=uuid.uuid4(),
        provider="gitlab",
        owner="group",
        name="proj",
        webhook_secret="gltoken",
    )

    async def fake_get_repository(_session, provider, owner, name):
        if (provider, owner, name) == ("gitlab", "group", "proj"):
            return fake_repo
        return None

    monkeypatch.setattr(webhooks, "get_repository", fake_get_repository)

    arq = FakeArq()
    app = FastAPI()
    app.include_router(webhooks.router)

    async def override_db():
        yield None

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[webhooks._get_arq] = lambda: arq

    client = TestClient(app)
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {
            "action": "open",
            "iid": 11,
            "last_commit": {"id": "cafebabe"},
        },
        "project": {"path_with_namespace": "group/proj"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-gitlab-event": "Merge Request Hook",
        "x-gitlab-token": "gltoken",
        "content-type": "application/json",
    }

    response = client.post("/webhook/gitlab", content=body, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["pr_number"] == 11
    assert data["commit_sha"] == "cafebabe"
    assert len(arq.jobs) == 1


def test_gitlab_webhook_rejects_bad_token(monkeypatch: pytest.MonkeyPatch):
    fake_repo = FakeRepo(
        id=uuid.uuid4(),
        provider="gitlab",
        owner="group",
        name="proj",
        webhook_secret="gltoken",
    )

    async def fake_get_repository(_session, provider, owner, name):
        if (provider, owner, name) == ("gitlab", "group", "proj"):
            return fake_repo
        return None

    monkeypatch.setattr(webhooks, "get_repository", fake_get_repository)

    arq = FakeArq()
    app = FastAPI()
    app.include_router(webhooks.router)

    async def override_db():
        yield None

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[webhooks._get_arq] = lambda: arq

    client = TestClient(app)
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {
            "action": "open",
            "iid": 11,
            "last_commit": {"id": "cafebabe"},
        },
        "project": {"path_with_namespace": "group/proj"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-gitlab-event": "Merge Request Hook",
        "x-gitlab-token": "wrong",
        "content-type": "application/json",
    }

    response = client.post("/webhook/gitlab", content=body, headers=headers)
    assert response.status_code == 401
    assert arq.jobs == []
