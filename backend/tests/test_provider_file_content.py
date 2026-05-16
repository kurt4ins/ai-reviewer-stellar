from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.providers.base import ProviderAPIError
from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider


@pytest.mark.asyncio
async def test_github_get_file_content_decodes_base64():
    raw = "def f():\n    return 1\n"
    encoded = base64.b64encode(raw.encode()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/widgets/contents/app/auth.py"
        assert request.url.params["ref"] == "abc123"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(
            200, json={"type": "file", "content": encoded, "encoding": "base64"}
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    content = await GitHubProvider.get_file_content(
        "tok", "acme", "widgets", "app/auth.py", "abc123", client=client
    )
    await client.aclose()
    assert content == raw


@pytest.mark.asyncio
async def test_github_get_file_content_404_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    with pytest.raises(ProviderAPIError):
        await GitHubProvider.get_file_content(
            "tok", "o", "r", "missing.py", "sha", client=client
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_github_search_code_returns_hits():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search/code"
        assert "sanitize repo:acme/widgets" in request.url.params["q"]
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "path": "app/sanitize.py",
                        "text_matches": [{"fragment": "def sanitize(value):"}],
                    },
                    {
                        "path": "app/util.py",
                        "text_matches": [{"fragment": "sanitize(arg)"}],
                    },
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    hits = await GitHubProvider.search_code(
        "tok", "acme", "widgets", "sanitize", client=client
    )
    await client.aclose()
    assert [h.path for h in hits] == ["app/sanitize.py", "app/util.py"]
    assert "def sanitize" in hits[0].snippet


@pytest.mark.asyncio
async def test_gitlab_get_file_content_decodes_base64():
    raw = "puts 'hi'\n"
    encoded = base64.b64encode(raw.encode()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/projects/grp/proj/repository/files/app/main.rb" in request.url.path
        assert request.url.params["ref"] == "cafebabe"
        assert request.headers["PRIVATE-TOKEN"] == "glt"
        return httpx.Response(200, json={"content": encoded, "encoding": "base64"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gl.test"
    )
    content = await GitLabProvider.get_file_content(
        "glt", "grp", "proj", "app/main.rb", "cafebabe", client=client
    )
    await client.aclose()
    assert content == raw


@pytest.mark.asyncio
async def test_gitlab_search_code_returns_hits():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/projects/grp/proj/search" in request.url.path
        assert request.url.params["scope"] == "blobs"
        assert request.url.params["search"] == "Sanitizer"
        return httpx.Response(
            200,
            content=json.dumps(
                [
                    {"path": "lib/sanitizer.rb", "data": "class Sanitizer"},
                    {"path": "lib/util.rb", "data": "Sanitizer.call(x)"},
                ]
            ),
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gl.test"
    )
    hits = await GitLabProvider.search_code(
        "glt", "grp", "proj", "Sanitizer", client=client
    )
    await client.aclose()
    assert [h.path for h in hits] == ["lib/sanitizer.rb", "lib/util.rb"]
