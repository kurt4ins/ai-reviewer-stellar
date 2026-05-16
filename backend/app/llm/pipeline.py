from __future__ import annotations

import logging
from dataclasses import dataclass

from app.llm.analyzer import analyze_hunk as run_analyzer
from app.llm.classifier import classify_hunk
from app.llm.critic import DEFAULT_CONFIDENCE_THRESHOLD, critique
from app.llm.schemas import RawFinding
from app.llm.tools import ToolContext
from app.security.cwe_list import cwes_for_language, detect_language
from app.utils.diff_parser import Hunk

logger = logging.getLogger("stellar.pipeline")


@dataclass(frozen=True)
class AnalyzedFinding:
    file_path: str
    cwe: str
    severity: str
    line_number: int
    description: str
    confidence: float
    fix_code: str | None
    fix_explanation: str | None


@dataclass(frozen=True)
class HunkAnalysis:
    file_path: str
    findings: list[AnalyzedFinding]
    skipped_reason: str | None = None


async def analyze_pull_request_hunk(
    *,
    classifier_model: str,
    analyzer_model: str,
    file_path: str,
    hunk: Hunk,
    tool_context: ToolContext | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> HunkAnalysis:
    language = detect_language(file_path)
    if language is None:
        return HunkAnalysis(file_path=file_path, findings=[], skipped_reason="unknown_language")

    catalog = cwes_for_language(language)
    if not catalog:
        return HunkAnalysis(file_path=file_path, findings=[], skipped_reason="no_applicable_cwes")

    rendered = hunk.render()
    allowed_cwes = {entry.id for entry in catalog}

    classifier_result = await classify_hunk(
        model=classifier_model,
        file_path=file_path,
        language=language,
        catalog=catalog,
        hunk_rendered=rendered,
    )
    logger.info(
        "classifier: file=%s lines=%s-%s status=%s findings=%d",
        file_path,
        hunk.new_start,
        hunk.new_end,
        classifier_result.status,
        len(classifier_result.findings),
    )

    if classifier_result.status == "clean" and not classifier_result.findings:
        return HunkAnalysis(file_path=file_path, findings=[], skipped_reason="classifier_clean")

    analyzer_result = await run_analyzer(
        model=analyzer_model,
        file_path=file_path,
        language=language,
        catalog=catalog,
        hunk_rendered=rendered,
        classifier_result=classifier_result,
        tool_context=tool_context,
    )
    logger.info(
        "analyzer: file=%s lines=%s-%s findings=%d",
        file_path,
        hunk.new_start,
        hunk.new_end,
        len(analyzer_result.findings),
    )

    accepted: list[RawFinding] = critique(
        analyzer_result.findings,
        allowed_cwes=allowed_cwes,
        hunk_min_line=hunk.new_start,
        hunk_max_line=hunk.new_end,
        confidence_threshold=confidence_threshold,
    )
    logger.info(
        "critic: file=%s lines=%s-%s accepted=%d",
        file_path,
        hunk.new_start,
        hunk.new_end,
        len(accepted),
    )

    findings = [
        AnalyzedFinding(
            file_path=file_path,
            cwe=f.cwe,
            severity=f.severity,
            line_number=f.line_number,
            description=f.description,
            confidence=f.confidence,
            fix_code=f.fix_code,
            fix_explanation=f.fix_explanation,
        )
        for f in accepted
    ]
    return HunkAnalysis(file_path=file_path, findings=findings)
