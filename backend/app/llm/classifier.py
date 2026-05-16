from __future__ import annotations

from typing import Any

from app.llm.client import complete
from app.llm.parsing import parse_classifier_response
from app.llm.prompts import CLASSIFIER_SYSTEM, build_classifier_user_prompt
from app.llm.schemas import CLASSIFIER_JSON_SCHEMA, ClassifierResult
from app.security.cwe_list import CweEntry

_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "classifier_result",
        "schema": CLASSIFIER_JSON_SCHEMA,
        "strict": True,
    },
}


async def classify_hunk(
    *,
    model: str,
    file_path: str,
    language: str,
    catalog: list[CweEntry],
    hunk_rendered: str,
) -> ClassifierResult:
    user_prompt = build_classifier_user_prompt(
        file_path=file_path,
        language=language,
        catalog=catalog,
        hunk_rendered=hunk_rendered,
    )
    message = await complete(
        model=model,
        messages=[
            {"role": "system", "content": CLASSIFIER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        response_format=_RESPONSE_FORMAT,
    )
    return parse_classifier_response(message.content or "")
