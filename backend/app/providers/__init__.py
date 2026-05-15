from __future__ import annotations

from app.providers.base import GitProvider
from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider

_REGISTRY: dict[str, type[GitProvider]] = {
    GitHubProvider.name: GitHubProvider,
    GitLabProvider.name: GitLabProvider,
}


def get_provider(name: str) -> type[GitProvider]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"unknown provider: {name}") from exc
