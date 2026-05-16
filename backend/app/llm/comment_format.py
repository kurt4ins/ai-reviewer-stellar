from __future__ import annotations

from app.llm.pipeline import AnalyzedFinding

_SEVERITY_ICON = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}


def render_finding_comment(finding: AnalyzedFinding) -> str:
    icon = _SEVERITY_ICON.get(finding.severity, "⚪")
    header = f"{icon} **{finding.cwe} · {finding.severity.upper()}** · _Stellar AI_"
    parts = [header, "", finding.description.strip()]

    if finding.fix_code:
        parts += ["", "```suggestion", finding.fix_code.rstrip(), "```"]
        if finding.fix_explanation:
            parts += ["", f"_{finding.fix_explanation.strip()}_"]
    elif finding.fix_explanation:
        parts += ["", f"_{finding.fix_explanation.strip()}_"]

    parts += ["", f"<sub>confidence: {finding.confidence:.2f}</sub>"]
    return "\n".join(parts)
