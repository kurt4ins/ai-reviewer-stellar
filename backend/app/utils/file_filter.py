from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatch

DEFAULT_IGNORE_GLOBS: tuple[str, ...] = (
    "README*",
    "CHANGELOG*",
    "LICENSE*",
    "CONTRIBUTING*",
    "CODE_OF_CONDUCT*",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".dockerignore",
    "*.md",
    "*.rst",
    "*.txt",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.bmp",
    "*.svg",
    "*.ico",
    "*.webp",
    "*.pdf",
    "*.mp3",
    "*.mp4",
    "*.mov",
    "*.avi",
    "*.webm",
    "*.zip",
    "*.tar",
    "*.tar.gz",
    "*.tgz",
    "*.gz",
    "*.bz2",
    "*.7z",
    "*.rar",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.otf",
    "*.eot",
    "*.min.js",
    "*.min.css",
    "*.map",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
    "*.snap",
)

DEFAULT_IGNORE_DIR_SEGMENTS: tuple[str, ...] = (
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    "__pycache__",
)


def should_ignore_file(path: str, extra_globs: Iterable[str] = ()) -> bool:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    segments = normalized.split("/")
    if any(seg in DEFAULT_IGNORE_DIR_SEGMENTS for seg in segments):
        return True
    basename = segments[-1]
    patterns = list(DEFAULT_IGNORE_GLOBS) + list(extra_globs or ())
    return any(
        fnmatch(normalized, pattern) or fnmatch(basename, pattern)
        for pattern in patterns
    )
