from __future__ import annotations

import json

import httpx
import pytest

from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider

GH_FILES = [
    {
        "filename": "auth.py",
        "status": "modified",
        "patch": "@@ -1,2 +1,3 @@\n a\n+b\n c",
    },
    {
        "filename": "logo.png",
        "status": "added",
    },
    {
        "filename": "new.py",
        "previous_filename": "old.py",
        "status": "renamed",
        "patch": "@@ -1 +1 @@\n-x\n+y",
    },
]


@pytest.mark.asyncio
async def test_github_get_pr_diff_maps_files():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/widgets/pulls/7/files"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json=GH_FILES)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    files = await GitHubProvider.get_pr_diff("tok", "acme", "widgets", 7, client=client)
    await client.aclose()

    assert [f.path for f in files] == ["auth.py", "logo.png", "new.py"]
    assert files[0].status == "modified"
    assert files[1].patch is None
    assert files[2].status == "renamed"
    assert files[2].old_path == "old.py"


@pytest.mark.asyncio
async def test_github_pagination_stops_on_short_page():
    calls: list[int] = []

    def _file(name: str) -> dict:
        return {"filename": name, "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"}

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        if page == 1:
            return httpx.Response(200, json=[_file(f"f{i}.py") for i in range(100)])
        return httpx.Response(200, json=[_file("last.py")])

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    files = await GitHubProvider.get_pr_diff("tok", "o", "r", 1, client=client)
    await client.aclose()

    assert calls == [1, 2]
    assert len(files) == 101


@pytest.mark.asyncio
async def test_gitlab_get_pr_diff_maps_changes():
    body = {
        "changes": [
            {
                "old_path": "auth.py",
                "new_path": "auth.py",
                "diff": "@@ -1 +1,2 @@\n a\n+b",
            },
            {
                "old_path": "a.py",
                "new_path": "b.py",
                "renamed_file": True,
                "diff": "",
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "merge_requests/3/changes" in request.url.path
        assert request.headers["PRIVATE-TOKEN"] == "glt"
        return httpx.Response(200, content=json.dumps(body))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gl.test"
    )
    files = await GitLabProvider.get_pr_diff("glt", "grp", "proj", 3, client=client)
    await client.aclose()

    assert files[0].path == "auth.py"
    assert files[0].status == "modified"
    assert files[1].status == "renamed"
    assert files[1].patch is None


@pytest.mark.asyncio
async def test_github_api_error_raises():
    from app.providers.base import ProviderAPIError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://gh.test"
    )
    with pytest.raises(ProviderAPIError):
        await GitHubProvider.get_pr_diff("tok", "o", "r", 1, client=client)
    await client.aclose()
