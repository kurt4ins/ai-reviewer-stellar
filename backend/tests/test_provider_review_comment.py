from __future__ import annotations

import json

import httpx
import pytest

from app.providers.base import ProviderAPIError
from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider


@pytest.mark.asyncio
async def test_github_post_review_comment_posts_inline():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(201, json={"id": 1234567})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    posted = await GitHubProvider.post_review_comment(
        "tok",
        "acme",
        "widgets",
        42,
        "abc123",
        "app/auth.py",
        7,
        "🔴 **CWE-89** SQLi",
        client=client,
    )
    await client.aclose()

    assert posted.provider_comment_id == "1234567"
    assert captured["path"] == "/repos/acme/widgets/pulls/42/comments"
    assert captured["auth"] == "Bearer tok"
    assert captured["body"]["commit_id"] == "abc123"
    assert captured["body"]["path"] == "app/auth.py"
    assert captured["body"]["line"] == 7
    assert captured["body"]["side"] == "RIGHT"
    assert captured["body"]["body"] == "🔴 **CWE-89** SQLi"


@pytest.mark.asyncio
async def test_github_post_review_comment_raises_on_422():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="line not part of diff")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    with pytest.raises(ProviderAPIError):
        await GitHubProvider.post_review_comment(
            "tok", "o", "r", 1, "sha", "f.py", 1, "body", client=client
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_gitlab_post_review_comment_fetches_diff_refs_and_creates_discussion():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith(
            "/merge_requests/7"
        ):
            return httpx.Response(
                200,
                json={
                    "diff_refs": {
                        "base_sha": "BASE",
                        "start_sha": "START",
                        "head_sha": "HEAD",
                    }
                },
            )
        if request.method == "POST" and request.url.path.endswith(
            "/merge_requests/7/discussions"
        ):
            captured["body"] = json.loads(request.content)
            captured["token"] = request.headers.get("PRIVATE-TOKEN")
            return httpx.Response(201, json={"id": "disc-xyz"})
        return httpx.Response(404, text="unexpected")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gl.test"
    )
    posted = await GitLabProvider.post_review_comment(
        "glt",
        "grp",
        "proj",
        7,
        "HEAD",
        "src/app.rb",
        10,
        "🟠 **CWE-79** XSS",
        client=client,
    )
    await client.aclose()

    assert posted.provider_comment_id == "disc-xyz"
    assert captured["token"] == "glt"
    pos = captured["body"]["position"]
    assert pos["base_sha"] == "BASE"
    assert pos["start_sha"] == "START"
    assert pos["head_sha"] == "HEAD"
    assert pos["new_path"] == "src/app.rb"
    assert pos["new_line"] == 10
    assert captured["body"]["body"] == "🟠 **CWE-79** XSS"


@pytest.mark.asyncio
async def test_gitlab_post_review_comment_raises_when_diff_refs_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"diff_refs": {}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gl.test"
    )
    with pytest.raises(ProviderAPIError):
        await GitLabProvider.post_review_comment(
            "glt", "grp", "proj", 1, "sha", "f.py", 1, "body", client=client
        )
    await client.aclose()
