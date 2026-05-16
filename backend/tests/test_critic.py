from __future__ import annotations

from app.llm.critic import critique
from app.llm.schemas import RawFinding


def _finding(
    *,
    cwe: str = "CWE-89",
    severity: str = "critical",
    line: int = 10,
    confidence: float = 0.9,
    description: str = "raw sql",
) -> RawFinding:
    return RawFinding(
        cwe=cwe,
        severity=severity,
        line_number=line,
        description=description,
        confidence=confidence,
    )


ALLOWED = {"CWE-89", "CWE-79", "CWE-798"}


def test_critique_filters_low_confidence():
    findings = [_finding(confidence=0.6), _finding(line=11, confidence=0.8)]
    result = critique(
        findings,
        allowed_cwes=ALLOWED,
        hunk_min_line=1,
        hunk_max_line=100,
    )
    assert len(result) == 1
    assert result[0].line_number == 11


def test_critique_drops_cwe_outside_allowed():
    findings = [_finding(cwe="CWE-200")]
    result = critique(
        findings,
        allowed_cwes=ALLOWED,
        hunk_min_line=1,
        hunk_max_line=100,
    )
    assert result == []


def test_critique_drops_lines_outside_hunk_range():
    findings = [_finding(line=5), _finding(cwe="CWE-79", line=200, severity="high")]
    result = critique(
        findings,
        allowed_cwes=ALLOWED,
        hunk_min_line=1,
        hunk_max_line=100,
    )
    assert len(result) == 1
    assert result[0].line_number == 5


def test_critique_dedupes_same_cwe_and_line():
    findings = [
        _finding(line=10, description="first"),
        _finding(line=10, description="duplicate"),
    ]
    result = critique(
        findings,
        allowed_cwes=ALLOWED,
        hunk_min_line=1,
        hunk_max_line=100,
    )
    assert len(result) == 1
    assert result[0].description == "first"


def test_critique_rejects_invalid_cwe_even_if_allowed_set_contains_it():
    findings = [_finding(cwe="CWE-9999")]
    result = critique(
        findings,
        allowed_cwes={"CWE-9999"},
        hunk_min_line=1,
        hunk_max_line=100,
    )
    assert result == []
