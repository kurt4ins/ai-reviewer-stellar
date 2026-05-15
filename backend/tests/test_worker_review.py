from __future__ import annotations

import logging

import pytest

from app.providers.base import ChangedFile
from app.workers import review


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeRepo:
    owner = "acme"
    name = "widgets"
    encrypted_token = "enc-blob"


class _FakeProvider:
    name = "github"

    @staticmethod
    async def get_pr_diff(token, owner, repo, pr_number):
        assert token == "plain-token"
        assert (owner, repo, pr_number) == ("acme", "widgets", 42)
        return [
            ChangedFile(
                path="auth.py",
                old_path=None,
                status="modified",
                patch="@@ -1,2 +1,3 @@\n a\n+import os\n b",
            ),
            ChangedFile(
                path="logo.png",
                old_path=None,
                status="added",
                patch=None,
            ),
        ]


@pytest.mark.asyncio
async def test_review_pull_request_extracts_diff(monkeypatch, caplog):
    async def fake_get_repo(session, repository_id):
        return _FakeRepo()

    monkeypatch.setattr(review, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(review, "get_repository_by_id", fake_get_repo)
    monkeypatch.setattr(review, "decrypt_token", lambda blob: "plain-token")
    monkeypatch.setattr(review, "get_provider", lambda name: _FakeProvider)

    with caplog.at_level(logging.INFO, logger="stellar.worker"):
        result = await review.review_pull_request(
            {},
            "github",
            "11111111-1111-1111-1111-111111111111",
            42,
            "abc123",
        )

    assert result["status"] == "diff_extracted"
    assert result["files"] == 2
    assert result["hunks"] == 1
    assert result["skipped"] == 1
    assert "Sending hunk to LLM: file=auth.py lines=1-3" in caplog.text


@pytest.mark.asyncio
async def test_review_pull_request_repository_not_found(monkeypatch):
    async def fake_get_repo(session, repository_id):
        return None

    monkeypatch.setattr(review, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(review, "get_repository_by_id", fake_get_repo)

    result = await review.review_pull_request({}, "github", "missing-id", 1, "sha")

    assert result["status"] == "repository_not_found"
