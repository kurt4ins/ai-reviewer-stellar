from __future__ import annotations

from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider


def test_github_parse_opened_pr():
    payload = {
        "action": "opened",
        "pull_request": {"number": 42, "head": {"sha": "abc123"}},
        "repository": {"full_name": "acme/widgets"},
    }
    event = GitHubProvider.parse_event({"x-github-event": "pull_request"}, payload)
    assert event is not None
    assert event.provider == "github"
    assert event.action == "opened"
    assert event.owner == "acme"
    assert event.repo == "widgets"
    assert event.pr_number == 42
    assert event.commit_sha == "abc123"


def test_github_ignores_ping():
    event = GitHubProvider.parse_event({"x-github-event": "ping"}, {})
    assert event is None


def test_github_ignores_closed_action():
    payload = {
        "action": "closed",
        "pull_request": {"number": 1, "head": {"sha": "x"}},
        "repository": {"full_name": "a/b"},
    }
    event = GitHubProvider.parse_event({"x-github-event": "pull_request"}, payload)
    assert event is None


def test_gitlab_parse_open_mr():
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {
            "action": "open",
            "iid": 7,
            "last_commit": {"id": "deadbeef"},
        },
        "project": {"path_with_namespace": "group/sub/proj"},
    }
    event = GitLabProvider.parse_event({"x-gitlab-event": "Merge Request Hook"}, payload)
    assert event is not None
    assert event.provider == "gitlab"
    assert event.action == "open"
    assert event.owner == "group/sub"
    assert event.repo == "proj"
    assert event.pr_number == 7
    assert event.commit_sha == "deadbeef"


def test_gitlab_ignores_unsupported_action():
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {"action": "close", "iid": 1, "last_commit": {"id": "x"}},
        "project": {"path_with_namespace": "a/b"},
    }
    event = GitLabProvider.parse_event({"x-gitlab-event": "Merge Request Hook"}, payload)
    assert event is None
