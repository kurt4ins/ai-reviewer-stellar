from __future__ import annotations

from app.llm.schemas import SEVERITIES, RawFinding
from app.security.cwe_list import get_cwe

DEFAULT_CONFIDENCE_THRESHOLD = 0.7


def critique(
    findings: list[RawFinding],
    *,
    allowed_cwes: set[str],
    hunk_min_line: int,
    hunk_max_line: int,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> list[RawFinding]:
    accepted: list[RawFinding] = []
    seen: set[tuple[str, int]] = set()
    for finding in findings:
        if finding.confidence < confidence_threshold:
            continue
        if finding.cwe not in allowed_cwes:
            continue
        if get_cwe(finding.cwe) is None:
            continue
        if finding.severity not in SEVERITIES:
            continue
        if finding.line_number < hunk_min_line or finding.line_number > hunk_max_line:
            continue
        key = (finding.cwe, finding.line_number)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(finding)
    return accepted
