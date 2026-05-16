from __future__ import annotations

import pytest

from app.llm.parsing import (
    LLMParseError,
    parse_analyzer_response,
    parse_classifier_response,
)


def test_classifier_parse_clean():
    raw = '{"status": "clean", "findings": []}'
    result = parse_classifier_response(raw)
    assert result.status == "clean"
    assert result.findings == []


def test_classifier_parse_with_fenced_json():
    raw = """```json
{"status": "found", "findings": [
  {"cwe": "CWE-89", "severity": "critical", "line_number": 12,
   "description": "raw sql", "confidence": 0.9}
], "questions": []}
```"""
    result = parse_classifier_response(raw)
    assert result.status == "found"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.cwe == "CWE-89"
    assert finding.line_number == 12
    assert finding.confidence == pytest.approx(0.9)


def test_classifier_drops_malformed_finding_but_keeps_valid_ones():
    raw = (
        '{"status": "found", "findings": ['
        '{"cwe": "CWE-79", "severity": "high", "line_number": 4, '
        ' "description": "xss", "confidence": 0.8},'
        '{"cwe": "CWE-89", "severity": "BAD", "line_number": 5, '
        ' "description": "x", "confidence": 0.9}'
        ']}'
    )
    result = parse_classifier_response(raw)
    assert len(result.findings) == 1
    assert result.findings[0].cwe == "CWE-79"


def test_classifier_invalid_status_raises():
    raw = '{"status": "weird", "findings": []}'
    with pytest.raises(LLMParseError):
        parse_classifier_response(raw)


def test_classifier_non_json_raises():
    with pytest.raises(LLMParseError):
        parse_classifier_response("not json at all")


def test_analyzer_parse_includes_fix_fields():
    raw = (
        '{"findings": [{"cwe": "CWE-798", "severity": "critical", '
        '"line_number": 3, "description": "hardcoded key", "confidence": 0.95, '
        '"fix_code": "API_KEY = os.environ[\\"API_KEY\\"]", '
        '"fix_explanation": "read from env"}]}'
    )
    result = parse_analyzer_response(raw)
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.fix_code is not None and "os.environ" in f.fix_code
    assert f.fix_explanation == "read from env"


def test_analyzer_confidence_clamped():
    raw = (
        '{"findings": [{"cwe": "CWE-79", "severity": "medium", '
        '"line_number": 1, "description": "xss", "confidence": 1.5}]}'
    )
    result = parse_analyzer_response(raw)
    assert result.findings[0].confidence == 1.0
