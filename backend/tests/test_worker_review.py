from __future__ import annotations

import uuid

import pytest

from app.llm.pipeline import AnalyzedFinding, HunkAnalysis
from app.providers.base import ChangedFile
from app.workers import review


class _FakeSession:
    def __init__(self, repo_obj):
        self._repo = repo_obj
        self.added: list[object] = []
        self.committed = 0
        self.flushed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.committed += 1

    async def get(self, model, key):
        return self._repo


class _FakeRepoRecord:
    id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    owner = "acme"
    name = "widgets"
    encrypted_token = "enc-blob"


class _FakeReviewRow:
    def __init__(self):
        self.id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        self.findings_count = 0
        self.critical_count = 0
        self.status = "running"


class _FakeProvider:
    name = "github"

    @staticmethod
    async def get_pr_diff(token, owner, repo, pr_number):
        assert token == "plain-token"
        assert (owner, repo, pr_number) == ("acme", "widgets", 42)
        return [
            ChangedFile(
                path="app/auth.py",
                old_path=None,
                status="modified",
                patch=(
                    "@@ -1,2 +1,3 @@\n"
                    " a\n"
                    "+import os\n"
                    " b"
                ),
            ),
            ChangedFile(
                path="logo.png",
                old_path=None,
                status="added",
                patch=None,
            ),
        ]


@pytest.mark.asyncio
async def test_review_pull_request_persists_findings(monkeypatch):
    review_row = _FakeReviewRow()
    sessions: list[_FakeSession] = []

    def session_factory():
        session = _FakeSession(review_row)
        sessions.append(session)
        return session

    async def fake_get_repo(session, repository_id):
        return _FakeRepoRecord()

    async def fake_create_review(session, *, repository_id, pr_number, commit_sha):
        return review_row

    finalize_calls: list[dict] = []

    async def fake_finalize(session, *, review, findings, status="completed"):
        review.findings = list(findings)
        review.findings_count = len(review.findings)
        review.critical_count = sum(1 for f in review.findings if f.severity == "critical")
        review.status = status
        finalize_calls.append({"count": len(review.findings)})
        return review

    async def fake_analyze(**kwargs):
        return HunkAnalysis(
            file_path=kwargs["file_path"],
            findings=[
                AnalyzedFinding(
                    file_path=kwargs["file_path"],
                    cwe="CWE-798",
                    severity="critical",
                    line_number=2,
                    description="hardcoded import marker",
                    confidence=0.9,
                    fix_code="import os  # ok",
                    fix_explanation="example",
                )
            ],
        )

    monkeypatch.setattr(review, "SessionLocal", session_factory)
    monkeypatch.setattr(review, "get_repository_by_id", fake_get_repo)
    monkeypatch.setattr(review, "create_review", fake_create_review)
    monkeypatch.setattr(review, "finalize_review", fake_finalize)
    monkeypatch.setattr(review, "decrypt_token", lambda blob: "plain-token")
    monkeypatch.setattr(review, "get_provider", lambda name: _FakeProvider)
    monkeypatch.setattr(review, "analyze_pull_request_hunk", fake_analyze)

    result = await review.review_pull_request(
        {},
        "github",
        "11111111-1111-1111-1111-111111111111",
        42,
        "abc123",
    )

    assert result["status"] == "completed"
    assert result["files"] == 2
    assert result["hunks"] == 1
    assert result["skipped_files"] == 1
    assert result["findings"] == 1
    assert result["review_id"] == str(review_row.id)
    assert len(finalize_calls) == 1
    assert finalize_calls[0]["count"] == 1


@pytest.mark.asyncio
async def test_review_pull_request_repository_not_found(monkeypatch):
    async def fake_get_repo(session, repository_id):
        return None

    monkeypatch.setattr(review, "SessionLocal", lambda: _FakeSession(None))
    monkeypatch.setattr(review, "get_repository_by_id", fake_get_repo)

    result = await review.review_pull_request({}, "github", "missing-id", 1, "sha")
    assert result["status"] == "repository_not_found"


@pytest.mark.asyncio
async def test_review_pull_request_marks_failed_on_diff_error(monkeypatch):
    review_row = _FakeReviewRow()

    def session_factory():
        return _FakeSession(review_row)

    async def fake_get_repo(session, repository_id):
        return _FakeRepoRecord()

    async def fake_create_review(session, *, repository_id, pr_number, commit_sha):
        return review_row

    failed_calls: list[object] = []

    async def fake_mark_failed(session, *, review):
        failed_calls.append(review)
        review.status = "failed"
        return review

    class _BrokenProvider:
        @staticmethod
        async def get_pr_diff(*args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(review, "SessionLocal", session_factory)
    monkeypatch.setattr(review, "get_repository_by_id", fake_get_repo)
    monkeypatch.setattr(review, "create_review", fake_create_review)
    monkeypatch.setattr(review, "mark_review_failed", fake_mark_failed)
    monkeypatch.setattr(review, "decrypt_token", lambda blob: "plain-token")
    monkeypatch.setattr(review, "get_provider", lambda name: _BrokenProvider)

    result = await review.review_pull_request({}, "github", str(_FakeRepoRecord.id), 1, "sha")
    assert result["status"] == "diff_fetch_failed"
    assert len(failed_calls) == 1
