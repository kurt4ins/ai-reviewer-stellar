from __future__ import annotations

import pytest

from app.llm import pipeline as pipeline_mod
from app.llm.pipeline import analyze_pull_request_hunk
from app.llm.schemas import AnalyzerResult, ClassifierResult, RawFinding
from app.utils.diff_parser import DiffLine, Hunk


def _hunk(start: int = 10, end: int = 12) -> Hunk:
    sql_line = '    q = "SELECT * FROM u WHERE id=" + uid'
    lines = [
        DiffLine(kind="context", content="def f():", new_lineno=start),
        DiffLine(kind="added", content=sql_line, new_lineno=start + 1),
        DiffLine(kind="added", content="    return db.execute(q)", new_lineno=start + 2),
    ]
    return Hunk(new_start=start, new_end=end, header="", lines=lines)


@pytest.mark.asyncio
async def test_pipeline_skips_unknown_language(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "classify_hunk", _fail_classifier)
    result = await analyze_pull_request_hunk(
        classifier_model="c",
        analyzer_model="a",
        file_path="README.md",
        hunk=_hunk(),
    )
    assert result.skipped_reason == "unknown_language"
    assert result.findings == []


@pytest.mark.asyncio
async def test_pipeline_clean_classifier_short_circuits(monkeypatch):
    async def fake_classify(**_):
        return ClassifierResult(status="clean", findings=[])

    monkeypatch.setattr(pipeline_mod, "classify_hunk", fake_classify)
    monkeypatch.setattr(pipeline_mod, "run_analyzer", _fail_analyzer)

    result = await analyze_pull_request_hunk(
        classifier_model="c",
        analyzer_model="a",
        file_path="auth.py",
        hunk=_hunk(),
    )
    assert result.skipped_reason == "classifier_clean"
    assert result.findings == []


@pytest.mark.asyncio
async def test_pipeline_runs_full_chain_and_filters_low_confidence(monkeypatch):
    classifier_findings = [
        RawFinding(
            cwe="CWE-89",
            severity="critical",
            line_number=11,
            description="suspected sql injection",
            confidence=0.7,
        ),
    ]

    async def fake_classify(**_):
        return ClassifierResult(status="found", findings=classifier_findings)

    async def fake_analyze(**_):
        return AnalyzerResult(
            findings=[
                RawFinding(
                    cwe="CWE-89",
                    severity="critical",
                    line_number=11,
                    description="confirmed sql injection",
                    confidence=0.95,
                    fix_code="db.execute('SELECT * FROM u WHERE id=%s', (uid,))",
                    fix_explanation="use parameterized query",
                ),
                RawFinding(
                    cwe="CWE-89",
                    severity="critical",
                    line_number=12,
                    description="low confidence noise",
                    confidence=0.3,
                ),
                RawFinding(
                    cwe="CWE-79",
                    severity="high",
                    line_number=300,
                    description="out of hunk range",
                    confidence=0.9,
                ),
            ]
        )

    monkeypatch.setattr(pipeline_mod, "classify_hunk", fake_classify)
    monkeypatch.setattr(pipeline_mod, "run_analyzer", fake_analyze)

    result = await analyze_pull_request_hunk(
        classifier_model="c",
        analyzer_model="a",
        file_path="app/auth.py",
        hunk=_hunk(start=10, end=12),
    )

    assert result.skipped_reason is None
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.cwe == "CWE-89"
    assert finding.line_number == 11
    assert finding.fix_code is not None
    assert finding.confidence == pytest.approx(0.95)


async def _fail_classifier(**_):
    raise AssertionError("classifier should not be called")


async def _fail_analyzer(**_):
    raise AssertionError("analyzer should not be called")
