from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from app.llm import analyzer as analyzer_mod
from app.llm.analyzer import analyze_hunk
from app.llm.schemas import ClassifierResult, RawFinding
from app.llm.tools import ToolContext
from app.providers.base import CodeSearchHit
from app.security.cwe_list import cwes_for_language


@dataclass
class _Func:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Func


@dataclass
class _Message:
    content: str | None = None
    tool_calls: list[_ToolCall] | None = None


class _StubProvider:
    files: ClassVar[dict[str, str]] = {"app/auth.py": "def sanitize(x):\n    return x.strip()\n"}
    hits: ClassVar[list[CodeSearchHit]] = []

    @staticmethod
    async def get_file_content(token, owner, repo, path, ref):
        return _StubProvider.files[path]

    @staticmethod
    async def search_code(token, owner, repo, query, *, limit=5):
        return _StubProvider.hits


def _ctx() -> ToolContext:
    return ToolContext(
        provider_cls=_StubProvider,
        token="tok",
        owner="acme",
        repo="widgets",
        commit_sha="abc123",
    )


def _classifier() -> ClassifierResult:
    return ClassifierResult(
        status="found",
        findings=[
            RawFinding(
                cwe="CWE-89",
                severity="critical",
                line_number=12,
                description="possible sqli",
                confidence=0.7,
            )
        ],
        questions=["does sanitize() exist?"],
    )


@pytest.mark.asyncio
async def test_analyzer_calls_tool_then_submits(monkeypatch):
    calls: list[dict[str, Any]] = []

    submit_args = json.dumps(
        {
            "findings": [
                {
                    "cwe": "CWE-89",
                    "severity": "critical",
                    "line_number": 12,
                    "description": "SQL injection confirmed",
                    "confidence": 0.95,
                    "fix_code": "db.execute('... WHERE id=%s', (uid,))",
                    "fix_explanation": "use parameterized query",
                }
            ]
        }
    )

    responses = iter(
        [
            _Message(
                content=None,
                tool_calls=[
                    _ToolCall(
                        id="call_1",
                        function=_Func(
                            name="get_file_content",
                            arguments=json.dumps({"path": "app/auth.py"}),
                        ),
                    )
                ],
            ),
            _Message(
                content=None,
                tool_calls=[
                    _ToolCall(
                        id="call_2",
                        function=_Func(name="submit_findings", arguments=submit_args),
                    )
                ],
            ),
        ]
    )

    async def fake_complete(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(analyzer_mod, "complete", fake_complete)

    result = await analyze_hunk(
        model="qwen",
        file_path="app/auth.py",
        language="python",
        catalog=cwes_for_language("python"),
        hunk_rendered="12: q = 'SELECT ...'",
        classifier_result=_classifier(),
        tool_context=_ctx(),
    )

    assert len(result.findings) == 1
    assert result.findings[0].cwe == "CWE-89"
    assert result.findings[0].fix_code is not None
    assert len(calls) == 2
    assert "tools" in calls[0]


@pytest.mark.asyncio
async def test_analyzer_handles_unknown_tool_call_then_recovers(monkeypatch):
    submit_args = json.dumps({"findings": []})
    responses = iter(
        [
            _Message(
                content=None,
                tool_calls=[
                    _ToolCall(
                        id="c1",
                        function=_Func(name="nonexistent_tool", arguments="{}"),
                    )
                ],
            ),
            _Message(
                content=None,
                tool_calls=[
                    _ToolCall(
                        id="c2",
                        function=_Func(name="submit_findings", arguments=submit_args),
                    )
                ],
            ),
        ]
    )

    async def fake_complete(**_):
        return next(responses)

    monkeypatch.setattr(analyzer_mod, "complete", fake_complete)

    result = await analyze_hunk(
        model="qwen",
        file_path="app/auth.py",
        language="python",
        catalog=cwes_for_language("python"),
        hunk_rendered="12: x",
        classifier_result=_classifier(),
        tool_context=_ctx(),
    )
    assert result.findings == []


@pytest.mark.asyncio
async def test_analyzer_no_tool_use_falls_back_to_content_parse(monkeypatch):
    async def fake_complete(**_):
        return _Message(
            content=json.dumps(
                {
                    "findings": [
                        {
                            "cwe": "CWE-798",
                            "severity": "critical",
                            "line_number": 3,
                            "description": "hardcoded api key",
                            "confidence": 0.9,
                            "fix_code": "API_KEY = os.environ['API_KEY']",
                            "fix_explanation": "read from env",
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(analyzer_mod, "complete", fake_complete)

    result = await analyze_hunk(
        model="qwen",
        file_path="app/auth.py",
        language="python",
        catalog=cwes_for_language("python"),
        hunk_rendered="3: API_KEY = 'sk-...'",
        classifier_result=_classifier(),
        tool_context=_ctx(),
    )
    assert len(result.findings) == 1
    assert result.findings[0].cwe == "CWE-798"


@pytest.mark.asyncio
async def test_analyzer_exhausts_iterations_returns_empty(monkeypatch):
    async def fake_complete(**_):
        return _Message(
            content=None,
            tool_calls=[
                _ToolCall(
                    id="loop",
                    function=_Func(
                        name="get_file_content",
                        arguments=json.dumps({"path": "app/auth.py"}),
                    ),
                )
            ],
        )

    monkeypatch.setattr(analyzer_mod, "complete", fake_complete)

    result = await analyze_hunk(
        model="qwen",
        file_path="app/auth.py",
        language="python",
        catalog=cwes_for_language("python"),
        hunk_rendered="1: x",
        classifier_result=_classifier(),
        tool_context=_ctx(),
    )
    assert result.findings == []


@pytest.mark.asyncio
async def test_analyzer_without_tool_context_skips_tool_loop(monkeypatch):
    async def fake_complete(**kwargs):
        assert "tools" not in kwargs
        return _Message(content=json.dumps({"findings": []}))

    monkeypatch.setattr(analyzer_mod, "complete", fake_complete)

    result = await analyze_hunk(
        model="qwen",
        file_path="app/auth.py",
        language="python",
        catalog=cwes_for_language("python"),
        hunk_rendered="1: x",
        classifier_result=_classifier(),
        tool_context=None,
    )
    assert result.findings == []
