from __future__ import annotations

import json
import logging
from typing import Any

from app.llm.client import LLMError, complete
from app.llm.parsing import LLMParseError, parse_analyzer_response
from app.llm.prompts import ANALYZER_SYSTEM, build_analyzer_user_prompt
from app.llm.schemas import AnalyzerResult, ClassifierResult, RawFinding
from app.llm.tools import TOOL_SCHEMAS, ToolContext, dispatch_tool
from app.security.cwe_list import CweEntry

logger = logging.getLogger("stellar.analyzer")

MAX_TOOL_ITERATIONS = 5


def _classifier_findings_to_json(result: ClassifierResult) -> str:
    payload = [
        {
            "cwe": f.cwe,
            "severity": f.severity,
            "line_number": f.line_number,
            "description": f.description,
            "confidence": f.confidence,
        }
        for f in result.findings
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _serialize_tool_call(call: Any) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {
            "name": call.function.name,
            "arguments": call.function.arguments or "{}",
        },
    }


def _coerce_submit_findings(raw_arguments: str) -> AnalyzerResult:
    try:
        data = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        raise LLMParseError(f"submit_findings: invalid JSON arguments: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMParseError("submit_findings: arguments must be an object")
    findings_raw = data.get("findings", [])
    if not isinstance(findings_raw, list):
        raise LLMParseError("submit_findings: findings must be a list")
    return parse_analyzer_response(json.dumps({"findings": findings_raw}))


async def analyze_hunk(
    *,
    model: str,
    file_path: str,
    language: str,
    catalog: list[CweEntry],
    hunk_rendered: str,
    classifier_result: ClassifierResult,
    tool_context: ToolContext | None = None,
) -> AnalyzerResult:
    user_prompt = build_analyzer_user_prompt(
        file_path=file_path,
        language=language,
        catalog=catalog,
        hunk_rendered=hunk_rendered,
        classifier_status=classifier_result.status,
        classifier_findings_json=_classifier_findings_to_json(classifier_result),
        classifier_questions=classifier_result.questions,
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ANALYZER_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    if tool_context is None:
        message = await complete(model=model, messages=messages)
        return parse_analyzer_response(message.content or "")

    for iteration in range(MAX_TOOL_ITERATIONS):
        message = await complete(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        tool_calls = list(message.tool_calls or [])

        if not tool_calls:
            content = message.content or ""
            if not content.strip():
                logger.warning(
                    "analyzer iter=%d returned empty content without tool calls", iteration
                )
                return AnalyzerResult(findings=[])
            try:
                return parse_analyzer_response(content)
            except LLMParseError as exc:
                logger.warning("analyzer fallback parse failed: %s", exc)
                return AnalyzerResult(findings=[])

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [_serialize_tool_call(call) for call in tool_calls],
        }
        messages.append(assistant_msg)

        submitted: AnalyzerResult | None = None
        for call in tool_calls:
            name = call.function.name
            args = call.function.arguments or "{}"
            if name == "submit_findings":
                try:
                    submitted = _coerce_submit_findings(args)
                except LLMParseError as exc:
                    logger.warning("submit_findings malformed: %s", exc)
                    submitted = AnalyzerResult(findings=[])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps({"status": "accepted"}),
                    }
                )
                continue

            result_text = await dispatch_tool(tool_context, name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result_text,
                }
            )

        if submitted is not None:
            return submitted

    logger.warning(
        "analyzer exhausted %d tool iterations without submit_findings, returning empty",
        MAX_TOOL_ITERATIONS,
    )
    return AnalyzerResult(findings=[])


__all__ = ["AnalyzerResult", "LLMError", "RawFinding", "analyze_hunk"]
