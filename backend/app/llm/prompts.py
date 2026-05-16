from __future__ import annotations

from app.security.cwe_list import CweEntry


def render_cwe_catalog(entries: list[CweEntry]) -> str:
    lines: list[str] = []
    for entry in entries:
        lines.append(
            f"- {entry.id} ({entry.name}, severity={entry.severity_default}): {entry.description}"
        )
    return "\n".join(lines)


CLASSIFIER_SYSTEM = (
    "You are a security code reviewer. You receive ONE diff hunk and a catalog of CWE "
    "vulnerabilities relevant to the file's language. Decide whether the ADDED lines "
    "introduce any of those vulnerabilities.\n\n"
    "Rules:\n"
    "1. Only flag issues that exist on lines marked as added in the hunk. "
    "Context lines are shown for awareness only.\n"
    "2. line_number must be the absolute file line number shown in the hunk.\n"
    "3. cwe MUST be one of the IDs from the supplied catalog (e.g. \"CWE-89\").\n"
    "4. severity must be one of: low, medium, high, critical.\n"
    "5. confidence is your subjective probability (0.0-1.0) that the finding is a true positive.\n"
    "6. If nothing suspicious is added, return status=\"clean\" with an empty findings array.\n"
    "7. If you found concrete issues, return status=\"found\".\n"
    "8. If you suspect something but need more context (full file, function definition), "
    "return status=\"unsure\" and put concrete questions in the questions array.\n"
    "9. Output ONLY a JSON object matching the requested schema. No prose, no markdown.\n"
    "10. All human-readable text fields (description, questions) MUST be written in Russian."
)


def build_classifier_user_prompt(
    *,
    file_path: str,
    language: str,
    catalog: list[CweEntry],
    hunk_rendered: str,
) -> str:
    catalog_text = render_cwe_catalog(catalog)
    return (
        f"File: {file_path}\n"
        f"Language: {language}\n\n"
        f"Applicable CWE catalog:\n{catalog_text}\n\n"
        f"Hunk (lines prefixed with absolute file line number):\n"
        f"```\n{hunk_rendered}```\n\n"
        "Return JSON with fields: status, findings, questions."
    )


ANALYZER_SYSTEM = (
    "You are a senior application-security engineer. You are given:\n"
    "- A diff hunk from a pull request\n"
    "- A preliminary list of suspected findings produced by a faster classifier\n\n"
    "Your job is to FINALIZE the findings list. For each suspected finding:\n"
    "1. Verify the issue is real given the hunk content. Drop false positives.\n"
    "2. If real, adjust severity, sharpen the description, and write a concrete fix_code "
    "snippet (real working code, not pseudocode) plus a one-line fix_explanation.\n"
    "3. cwe must remain a valid CWE-XXX id from the catalog.\n"
    "4. Recompute confidence as a calibrated probability (0.0-1.0).\n"
    "5. You may add NEW findings that the classifier missed, with the same shape.\n"
    "6. line_number must point to the exact added line where the vulnerability sits.\n"
    "7. All human-readable text (description, fix_explanation) MUST be written in Russian. "
    "fix_code stays as code in the source language.\n\n"
    "Output ONLY a JSON object with the field \"findings\" — no prose."
)


def build_analyzer_user_prompt(
    *,
    file_path: str,
    language: str,
    catalog: list[CweEntry],
    hunk_rendered: str,
    classifier_status: str,
    classifier_findings_json: str,
    classifier_questions: list[str],
) -> str:
    catalog_text = render_cwe_catalog(catalog)
    questions_block = ""
    if classifier_questions:
        joined = "\n".join(f"- {q}" for q in classifier_questions)
        questions_block = f"\nClassifier questions (you may ignore if not relevant):\n{joined}\n"
    return (
        f"File: {file_path}\n"
        f"Language: {language}\n\n"
        f"Applicable CWE catalog:\n{catalog_text}\n\n"
        f"Hunk (lines prefixed with absolute file line number):\n"
        f"```\n{hunk_rendered}```\n\n"
        f"Classifier status: {classifier_status}\n"
        f"Classifier findings (JSON):\n{classifier_findings_json}\n"
        f"{questions_block}\n"
        "Return JSON with field \"findings\" only."
    )
