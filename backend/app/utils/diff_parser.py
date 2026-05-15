from __future__ import annotations

from dataclasses import dataclass

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError


@dataclass(frozen=True)
class DiffLine:
    kind: str
    content: str
    new_lineno: int


@dataclass(frozen=True)
class Hunk:
    new_start: int
    new_end: int
    header: str
    lines: list[DiffLine]

    @property
    def added_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "added"]

    def render(self) -> str:
        return "".join(
            f"{line.new_lineno}: {line.content}\n" for line in self.lines
        )


def parse_patch(path: str, patch: str) -> list[Hunk]:
    if not patch.strip():
        return []

    synthetic = f"--- a/{path}\n+++ b/{path}\n{patch}"
    if not synthetic.endswith("\n"):
        synthetic += "\n"

    try:
        patch_set = PatchSet(synthetic)
    except (UnidiffParseError, ValueError):
        return []

    if not patch_set:
        return []

    patched_file = patch_set[0]
    hunks: list[Hunk] = []
    for raw_hunk in patched_file:
        lines: list[DiffLine] = []
        for line in raw_hunk:
            if line.is_removed:
                continue
            kind = "added" if line.is_added else "context"
            lines.append(
                DiffLine(
                    kind=kind,
                    content=line.value.rstrip("\n"),
                    new_lineno=line.target_line_no,
                )
            )
        if not lines:
            continue
        new_start = raw_hunk.target_start
        new_end = raw_hunk.target_start + raw_hunk.target_length - 1
        hunks.append(
            Hunk(
                new_start=new_start,
                new_end=new_end,
                header=raw_hunk.section_header or "",
                lines=lines,
            )
        )
    return hunks
