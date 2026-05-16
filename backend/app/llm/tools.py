from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.providers.base import GitProvider, ProviderAPIError

logger = logging.getLogger("stellar.tools")

MAX_FILE_CHARS = 20_000
MAX_LINES_RANGE = 400


@dataclass
class ToolContext:
    provider_cls: type[GitProvider]
    token: str
    owner: str
    repo: str
    commit_sha: str
    file_cache: dict[str, str] = field(default_factory=dict)


_FINDING_ITEM_SCHEMA: dict[str, Any] = {
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
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "line_number": {"type": "integer"},
        "description": {"type": "string"},
        "confidence": {"type": "number"},
        "fix_code": {"type": "string"},
        "fix_explanation": {"type": "string"},
    },
}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": (
                "Read the full content of a source file at the pull-request commit. "
                "Returns up to ~20k characters; use get_lines for larger files. "
                "Use when you need to inspect imports, helpers, or sanitizers "
                "referenced from the hunk."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository-relative file path",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lines",
            "description": (
                "Read a line range from a file at the pull-request commit. "
                "Prefer this over get_file_content for large files."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "start_line", "end_line"],
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_repo",
            "description": (
                "Search code in the repository (current default branch index). "
                "Returns up to 5 file paths with matched snippets. "
                "Use to locate definitions of functions/sanitizers referenced from the hunk."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findings",
            "description": (
                "Submit the final list of vulnerabilities and finish analysis. "
                "MUST be called exactly once when you are done. "
                "Pass an empty list if no real vulnerabilities remain."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["findings"],
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": _FINDING_ITEM_SCHEMA,
                    }
                },
            },
        },
    },
]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, original {len(text)} chars]"


async def _load_file(ctx: ToolContext, path: str) -> str:
    if path in ctx.file_cache:
        return ctx.file_cache[path]
    content = await ctx.provider_cls.get_file_content(
        ctx.token, ctx.owner, ctx.repo, path, ctx.commit_sha
    )
    ctx.file_cache[path] = content
    return content


async def _tool_get_file_content(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return json.dumps({"error": "path is required"})
    try:
        content = await _load_file(ctx, path)
    except ProviderAPIError as exc:
        return json.dumps({"error": f"could not load file: {exc}"})
    return json.dumps({"path": path, "content": _truncate(content, MAX_FILE_CHARS)})


async def _tool_get_lines(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = str(args.get("path", "")).strip()
    try:
        start_line = int(args["start_line"])
        end_line = int(args["end_line"])
    except (KeyError, TypeError, ValueError):
        return json.dumps({"error": "start_line and end_line must be integers"})
    if not path:
        return json.dumps({"error": "path is required"})
    if start_line < 1 or end_line < start_line:
        return json.dumps({"error": "invalid line range"})
    if end_line - start_line + 1 > MAX_LINES_RANGE:
        end_line = start_line + MAX_LINES_RANGE - 1

    try:
        content = await _load_file(ctx, path)
    except ProviderAPIError as exc:
        return json.dumps({"error": f"could not load file: {exc}"})

    file_lines = content.splitlines()
    selected = file_lines[start_line - 1 : end_line]
    numbered = "\n".join(
        f"{start_line + idx}: {line}" for idx, line in enumerate(selected)
    )
    return json.dumps(
        {
            "path": path,
            "start_line": start_line,
            "end_line": start_line + len(selected) - 1,
            "lines": numbered,
        }
    )


async def _tool_search_in_repo(ctx: ToolContext, args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return json.dumps({"error": "query is required"})
    try:
        hits = await ctx.provider_cls.search_code(
            ctx.token, ctx.owner, ctx.repo, query, limit=5
        )
    except ProviderAPIError as exc:
        return json.dumps({"error": f"search failed: {exc}", "hits": []})
    return json.dumps(
        {
            "query": query,
            "hits": [
                {"path": hit.path, "snippet": _truncate(hit.snippet, 600)}
                for hit in hits
            ],
        }
    )


_DISPATCH = {
    "get_file_content": _tool_get_file_content,
    "get_lines": _tool_get_lines,
    "search_in_repo": _tool_search_in_repo,
}


async def dispatch_tool(ctx: ToolContext, name: str, raw_arguments: str) -> str:
    handler = _DISPATCH.get(name)
    if handler is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        args = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "invalid JSON arguments"})
    if not isinstance(args, dict):
        return json.dumps({"error": "arguments must be a JSON object"})
    try:
        return await handler(ctx, args)
    except Exception as exc:
        logger.exception("tool %s crashed: %s", name, exc)
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
