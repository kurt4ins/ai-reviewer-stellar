from __future__ import annotations

import uuid
from typing import ClassVar

import pytest

from app.llm.pipeline import AnalyzedFinding, HunkAnalysis
from app.providers.base import ChangedFile, PostedComment, ProviderAPIError
from app.workers import review


class _FakeSession:
    def __init__(self, repo_obj, findings=None):
        self._repo = repo_obj
        self._findings = list(findings or [])
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

    async def execute(self, stmt):
        return _FakeResult(self._findings)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeRepoRecord:
    id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    owner = "acme"
    name = "widgets"
    block_critical_merge = True
    ignore_globs: ClassVar[list[str]] = []


class _FakeReviewRow:
    def __init__(self):
        self.id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        self.findings_count = 0
        self.critical_count = 0
        self.status = "running"


class _FakeFindingRow:
    def __init__(self, line=2, cwe="CWE-798", severity="critical"):
        self.id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        self.file_path = "app/auth.py"
        self.line_number = line
        self.cwe = cwe
        self.severity = severity
        self.description = "hardcoded import marker"
        self.fix_code = "import os  # ok"
        self.fix_explanation = "example"
        self.confidence = 0.9


class _FakeProvider:
    name = "github"
    posted: ClassVar[list[dict]] = []
    statuses: ClassVar[list[dict]] = []

    @staticmethod
    async def get_pr_diff(token, owner, repo, pr_number):
        assert token == "bot-token"
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

    @staticmethod
    async def post_review_comment(
        token, owner, repo, pr_number, commit_sha, path, line, body
    ):
        _FakeProvider.posted.append(
            {
                "token": token,
                "path": path,
                "line": line,
                "body": body,
                "commit_sha": commit_sha,
            }
        )
        return PostedComment(provider_comment_id=f"gh-{len(_FakeProvider.posted)}")

    @staticmethod
    async def set_commit_status(
        token, owner, repo, commit_sha, state, description, **kwargs
    ):
        _FakeProvider.statuses.append(
            {
                "commit_sha": commit_sha,
                "state": state,
                "description": description,
            }
        )


@pytest.fixture(autouse=True)
def _bot_token_env(monkeypatch):
    monkeypatch.setenv("GITHUB_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("GITLAB_BOT_TOKEN", "bot-token")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_provider():
    _FakeProvider.posted.clear()
    _FakeProvider.statuses.clear()
    yield


@pytest.mark.asyncio
async def test_review_pull_request_persists_findings_and_posts_comments(monkeypatch):
    review_row = _FakeReviewRow()
    finding_row = _FakeFindingRow()

    def session_factory():
        return _FakeSession(review_row, findings=[finding_row])

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

    thread_records: list[dict] = []

    async def fake_record_thread(session, *, finding_id, provider_comment_id):
        thread_records.append(
            {"finding_id": finding_id, "provider_comment_id": provider_comment_id}
        )

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
    monkeypatch.setattr(review, "record_review_thread", fake_record_thread)
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
    assert result["posted"] == 1
    assert result["post_errors"] == 0
    assert len(finalize_calls) == 1
    assert len(_FakeProvider.posted) == 1
    posted = _FakeProvider.posted[0]
    assert posted["path"] == "app/auth.py"
    assert posted["line"] == 2
    assert "```suggestion" in posted["body"]
    assert "CWE-798" in posted["body"]
    assert len(thread_records) == 1
    assert thread_records[0]["provider_comment_id"] == "gh-1"
    assert result["merge_status"] == "failure"
    assert len(_FakeProvider.statuses) == 1
    status = _FakeProvider.statuses[0]
    assert status["state"] == "failure"
    assert status["commit_sha"] == "abc123"
    assert "1 critical" in status["description"]


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
    monkeypatch.setattr(review, "get_provider", lambda name: _BrokenProvider)

    result = await review.review_pull_request({}, "github", str(_FakeRepoRecord.id), 1, "sha")
    assert result["status"] == "diff_fetch_failed"
    assert len(failed_calls) == 1


@pytest.mark.asyncio
async def test_review_pull_request_tolerates_post_errors(monkeypatch):
    review_row = _FakeReviewRow()
    finding_row = _FakeFindingRow()

    def session_factory():
        return _FakeSession(review_row, findings=[finding_row])

    async def fake_get_repo(session, repository_id):
        return _FakeRepoRecord()

    async def fake_create_review(session, *, repository_id, pr_number, commit_sha):
        return review_row

    async def fake_finalize(session, *, review, findings, status="completed"):
        review.status = status
        return review

    async def fake_record_thread(session, *, finding_id, provider_comment_id):
        raise AssertionError("should not be called when post fails")

    async def fake_analyze(**kwargs):
        return HunkAnalysis(
            file_path=kwargs["file_path"],
            findings=[
                AnalyzedFinding(
                    file_path=kwargs["file_path"],
                    cwe="CWE-798",
                    severity="critical",
                    line_number=2,
                    description="x",
                    confidence=0.9,
                    fix_code=None,
                    fix_explanation=None,
                )
            ],
        )

    class _FlakyProvider(_FakeProvider):
        @staticmethod
        async def post_review_comment(*args, **kwargs):
            raise ProviderAPIError("403")

    monkeypatch.setattr(review, "SessionLocal", session_factory)
    monkeypatch.setattr(review, "get_repository_by_id", fake_get_repo)
    monkeypatch.setattr(review, "create_review", fake_create_review)
    monkeypatch.setattr(review, "finalize_review", fake_finalize)
    monkeypatch.setattr(review, "record_review_thread", fake_record_thread)
    monkeypatch.setattr(review, "get_provider", lambda name: _FlakyProvider)
    monkeypatch.setattr(review, "analyze_pull_request_hunk", fake_analyze)

    result = await review.review_pull_request(
        {}, "github", "11111111-1111-1111-1111-111111111111", 42, "abc123"
    )
    assert result["status"] == "completed"
    assert result["posted"] == 0
    assert result["post_errors"] == 1
