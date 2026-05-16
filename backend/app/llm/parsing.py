from __future__ import annotations

import json
import re
from typing import Any

from app.llm.schemas import (
    SEVERITIES,
    STATUSES,
    AnalyzerResult,
    ClassifierResult,
    RawFinding,
)


class LLMParseError(ValueError):
    pass


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)


def _strip_fences(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped).strip()
    return stripped


def _load_json(content: str) -> dict[str, Any]:
    text = _strip_fences(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMParseError(f"invalid JSON from LLM: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMParseError("LLM response is not a JSON object")
    return data


def _coerce_finding(item: Any) -> RawFinding | None:
    if not isinstance(item, dict):
        return None
    try:
        cwe = str(item["cwe"]).strip()
        severity = str(item["severity"]).strip().lower()
        line_number = int(item["line_number"])
        description = str(item["description"]).strip()
        confidence = float(item["confidence"])
    except (KeyError, TypeError, ValueError):
        return None
    if severity not in SEVERITIES:
        return None
    if not cwe or not description:
        return None
    fix_code_raw = item.get("fix_code")
    fix_explanation_raw = item.get("fix_explanation")
    return RawFinding(
        cwe=cwe,
        severity=severity,
        line_number=line_number,
        description=description,
        confidence=max(0.0, min(1.0, confidence)),
        fix_code=str(fix_code_raw) if fix_code_raw else None,
        fix_explanation=str(fix_explanation_raw) if fix_explanation_raw else None,
    )


def parse_classifier_response(content: str) -> ClassifierResult:
    data = _load_json(content)
    status = str(data.get("status", "")).strip().lower()
    if status not in STATUSES:
        raise LLMParseError(f"classifier returned unknown status: {status!r}")
    findings_raw = data.get("findings") or []
    if not isinstance(findings_raw, list):
        raise LLMParseError("classifier findings is not a list")
    findings = [f for f in (_coerce_finding(item) for item in findings_raw) if f is not None]
    questions_raw = data.get("questions") or []
    questions = [str(q) for q in questions_raw if isinstance(q, str) and q.strip()]
    return ClassifierResult(status=status, findings=findings, questions=questions)


def parse_analyzer_response(content: str) -> AnalyzerResult:
    data = _load_json(content)
    findings_raw = data.get("findings") or []
    if not isinstance(findings_raw, list):
        raise LLMParseError("analyzer findings is not a list")
    findings = [f for f in (_coerce_finding(item) for item in findings_raw) if f is not None]
    return AnalyzerResult(findings=findings)
