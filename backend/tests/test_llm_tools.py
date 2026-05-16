from __future__ import annotations

import json
from typing import ClassVar

import pytest

from app.llm.tools import MAX_FILE_CHARS, MAX_LINES_RANGE, ToolContext, dispatch_tool
from app.providers.base import CodeSearchHit, ProviderAPIError


class _FakeProvider:
    files: ClassVar[dict[str, str]] = {}
    search_hits: ClassVar[list[CodeSearchHit]] = []
    file_calls: ClassVar[list[tuple[str, str]]] = []
    raise_on_search: bool = False

    @staticmethod
    async def get_file_content(token, owner, repo, path, ref):
        _FakeProvider.file_calls.append((path, ref))
        if path in _FakeProvider.files:
            return _FakeProvider.files[path]
        raise ProviderAPIError(f"missing {path}")

    @staticmethod
    async def search_code(token, owner, repo, query, *, limit=5):
        if _FakeProvider.raise_on_search:
            raise ProviderAPIError("rate limited")
        return _FakeProvider.search_hits[:limit]


def _fresh_ctx() -> ToolContext:
    _FakeProvider.files = {}
    _FakeProvider.search_hits = []
    _FakeProvider.file_calls = []
    _FakeProvider.raise_on_search = False
    return ToolContext(
        provider_cls=_FakeProvider,
        token="tok",
        owner="acme",
        repo="widgets",
        commit_sha="abc123",
    )


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error():
    ctx = _fresh_ctx()
    result = json.loads(await dispatch_tool(ctx, "wat", "{}"))
    assert "error" in result


@pytest.mark.asyncio
async def test_get_file_content_caches_calls():
    ctx = _fresh_ctx()
    _FakeProvider.files["app/auth.py"] = "def hello():\n    pass\n"

    args = json.dumps({"path": "app/auth.py"})
    a = json.loads(await dispatch_tool(ctx, "get_file_content", args))
    b = json.loads(await dispatch_tool(ctx, "get_file_content", args))

    assert a["content"] == "def hello():\n    pass\n"
    assert b["content"] == a["content"]
    assert len(_FakeProvider.file_calls) == 1


@pytest.mark.asyncio
async def test_get_file_content_propagates_provider_error_as_json():
    ctx = _fresh_ctx()
    args = json.dumps({"path": "nope.py"})
    result = json.loads(await dispatch_tool(ctx, "get_file_content", args))
    assert "error" in result


@pytest.mark.asyncio
async def test_get_file_content_truncates_large_files():
    ctx = _fresh_ctx()
    _FakeProvider.files["big.py"] = "x" * (MAX_FILE_CHARS * 2)
    args = json.dumps({"path": "big.py"})
    result = json.loads(await dispatch_tool(ctx, "get_file_content", args))
    assert "truncated" in result["content"]
    assert result["content"].startswith("x" * 100)


@pytest.mark.asyncio
async def test_get_lines_returns_numbered_range():
    ctx = _fresh_ctx()
    _FakeProvider.files["a.py"] = "\n".join(f"line{i}" for i in range(1, 11))
    args = json.dumps({"path": "a.py", "start_line": 3, "end_line": 5})
    result = json.loads(await dispatch_tool(ctx, "get_lines", args))
    assert result["lines"].splitlines() == ["3: line3", "4: line4", "5: line5"]
    assert result["start_line"] == 3
    assert result["end_line"] == 5


@pytest.mark.asyncio
async def test_get_lines_clamps_to_max_range():
    ctx = _fresh_ctx()
    _FakeProvider.files["a.py"] = "\n".join(f"l{i}" for i in range(1, MAX_LINES_RANGE + 100))
    args = json.dumps({"path": "a.py", "start_line": 1, "end_line": MAX_LINES_RANGE + 50})
    result = json.loads(await dispatch_tool(ctx, "get_lines", args))
    assert result["end_line"] == MAX_LINES_RANGE


@pytest.mark.asyncio
async def test_get_lines_rejects_bad_range():
    ctx = _fresh_ctx()
    args = json.dumps({"path": "a.py", "start_line": 5, "end_line": 2})
    result = json.loads(await dispatch_tool(ctx, "get_lines", args))
    assert "error" in result


@pytest.mark.asyncio
async def test_search_in_repo_passes_hits():
    ctx = _fresh_ctx()
    _FakeProvider.search_hits = [
        CodeSearchHit(path="a.py", snippet="def sanitize(x)"),
        CodeSearchHit(path="b.py", snippet="sanitize(value)"),
    ]
    args = json.dumps({"query": "sanitize"})
    result = json.loads(await dispatch_tool(ctx, "search_in_repo", args))
    assert [h["path"] for h in result["hits"]] == ["a.py", "b.py"]


@pytest.mark.asyncio
async def test_search_in_repo_returns_error_on_provider_failure():
    ctx = _fresh_ctx()
    _FakeProvider.raise_on_search = True
    args = json.dumps({"query": "x"})
    result = json.loads(await dispatch_tool(ctx, "search_in_repo", args))
    assert "error" in result
    assert result["hits"] == []


@pytest.mark.asyncio
async def test_dispatch_invalid_json_arguments_returns_error():
    ctx = _fresh_ctx()
    result = json.loads(await dispatch_tool(ctx, "get_file_content", "not-json"))
    assert "error" in result
