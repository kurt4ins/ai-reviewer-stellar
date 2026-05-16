from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("low", "medium", "high", "critical")
STATUSES = ("clean", "found", "unsure")


CLASSIFIER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "findings"],
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "cwe",
                    "severity",
                    "line_number",
                    "description",
                    "confidence",
                ],
                "properties": {
                    "cwe": {"type": "string"},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "line_number": {"type": "integer"},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
        "questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


ANALYZER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "cwe",
                    "severity",
                    "line_number",
                    "description",
                    "confidence",
                ],
                "properties": {
                    "cwe": {"type": "string"},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "line_number": {"type": "integer"},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                    "fix_code": {"type": "string"},
                    "fix_explanation": {"type": "string"},
                },
            },
        },
    },
}


@dataclass(frozen=True)
class RawFinding:
    cwe: str
    severity: str
    line_number: int
    description: str
    confidence: float
    fix_code: str | None = None
    fix_explanation: str | None = None


@dataclass(frozen=True)
class ClassifierResult:
    status: str
    findings: list[RawFinding] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnalyzerResult:
    findings: list[RawFinding] = field(default_factory=list)
