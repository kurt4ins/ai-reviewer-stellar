from __future__ import annotations

from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import get_settings


class LLMError(RuntimeError):
    pass


@lru_cache
def get_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise LLMError("OPENROUTER_API_KEY is not configured")
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        default_headers={
            "HTTP-Referer": settings.webhook_base_url,
            "X-Title": "Stellar AI Reviewer",
        },
    )


async def complete(
    model: str,
    messages: list[dict[str, Any]],
    *,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    temperature: float = 0.0,
) -> ChatCompletionMessage:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice

    try:
        response = await get_client().chat.completions.create(**kwargs)
    except Exception as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    if not response.choices:
        raise LLMError("LLM returned no choices")
    return response.choices[0].message
