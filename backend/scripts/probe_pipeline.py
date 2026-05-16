from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.llm.pipeline import analyze_pull_request_hunk
from app.utils.diff_parser import parse_patch

SAMPLES_DIR = Path(__file__).parent / "samples"


SAMPLE_PATCHES: dict[str, tuple[str, str]] = {
    "sqli": (
        "app/users.py",
        "@@ -1 +1,4 @@\n"
        " from db import conn\n"
        "+def get_user(uid):\n"
        '+    q = "SELECT * FROM users WHERE id=" + uid\n'
        "+    return conn.execute(q).fetchone()\n",
    ),
    "hardcoded": (
        "app/settings.py",
        "@@ -1 +1,3 @@\n"
        " import os\n"
        '+API_KEY = "sk-live-AKIAIOSFODNN7EXAMPLE"\n'
        '+JWT_SECRET = "supersecret123"\n',
    ),
    "xss": (
        "src/render.js",
        "@@ -1,2 +1,4 @@\n"
        " export function render(comment) {\n"
        '+    const node = document.getElementById("c");\n'
        "+    node.innerHTML = comment;\n"
        " }\n",
    ),
    "clean": (
        "app/utils.py",
        "@@ -1 +1,3 @@\n"
        " import math\n"
        "+def area(r):\n"
        "+    return math.pi * r * r\n",
    ),
}


async def run_sample(name: str) -> None:
    if name not in SAMPLE_PATCHES:
        raise SystemExit(f"unknown sample: {name}. Known: {list(SAMPLE_PATCHES)}")
    file_path, patch = SAMPLE_PATCHES[name]
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is empty in .env")

    hunks = parse_patch(file_path, patch)
    if not hunks:
        raise SystemExit("no hunks parsed from sample patch")

    print(f"=== sample={name} file={file_path} ===")
    print(f"classifier_model = {settings.default_classifier_model}")
    print(f"analyzer_model   = {settings.default_analyzer_model}")
    for i, hunk in enumerate(hunks):
        print(f"\n--- hunk {i} lines {hunk.new_start}-{hunk.new_end} ---")
        print(hunk.render())
        result = await analyze_pull_request_hunk(
            classifier_model=settings.default_classifier_model,
            analyzer_model=settings.default_analyzer_model,
            file_path=file_path,
            hunk=hunk,
            tool_context=None,
        )
        if result.skipped_reason:
            print(f"skipped: {result.skipped_reason}")
            continue
        if not result.findings:
            print("no findings after critic")
            continue
        for f in result.findings:
            print(
                json.dumps(
                    {
                        "cwe": f.cwe,
                        "severity": f.severity,
                        "line": f.line_number,
                        "confidence": f.confidence,
                        "description": f.description,
                        "fix_code": f.fix_code,
                        "fix_explanation": f.fix_explanation,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the F3 pipeline on a built-in sample hunk.")
    parser.add_argument(
        "sample",
        nargs="?",
        default="sqli",
        help=f"one of: {', '.join(SAMPLE_PATCHES)}",
    )
    parser.add_argument("--all", action="store_true", help="run every sample sequentially")
    args = parser.parse_args()

    async def _run() -> None:
        names = list(SAMPLE_PATCHES) if args.all else [args.sample]
        for name in names:
            await run_sample(name)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
