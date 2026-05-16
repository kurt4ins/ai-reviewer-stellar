from __future__ import annotations

import pytest

from app.utils.file_filter import should_ignore_file


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/README.md",
        "CHANGELOG.md",
        ".gitignore",
        "frontend/.gitignore",
        "logo.png",
        "assets/images/banner.jpg",
        "fonts/Inter.woff2",
        "package-lock.json",
        "frontend/yarn.lock",
        "uv.lock",
        "dist/bundle.min.js",
        "src/app.min.css",
        "src/app.js.map",
        "node_modules/foo/index.js",
        "backend/__pycache__/cache.cpython-312.pyc",
    ],
)
def test_ignores_known_noise(path):
    assert should_ignore_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "app/main.py",
        "src/components/Button.tsx",
        "backend/app/llm/client.py",
        "Dockerfile",
        "compose.yaml",
    ],
)
def test_keeps_source_files(path):
    assert not should_ignore_file(path)


def test_extra_globs_extend_defaults():
    assert should_ignore_file("migrations/0001_init.sql", ["migrations/*"])
    assert not should_ignore_file("app/main.py", ["migrations/*"])
