from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WebhookEvent:
    provider: str
    event_type: str
    action: str
    owner: str
    repo: str
    pr_number: int
    commit_sha: str


@dataclass(frozen=True)
class ChangedFile:
    path: str
    old_path: str | None
    status: str
    patch: str | None


@dataclass(frozen=True)
class CodeSearchHit:
    path: str
    snippet: str


class SignatureError(Exception):
    pass


class ProviderAPIError(Exception):
    pass


class GitProvider(ABC):
    name: str

    @staticmethod
    @abstractmethod
    def verify_signature(secret: str, raw_body: bytes, headers: dict[str, str]) -> None:
        ...

    @staticmethod
    @abstractmethod
    def parse_event(headers: dict[str, str], payload: dict) -> WebhookEvent | None:
        ...

    @staticmethod
    @abstractmethod
    async def get_pr_diff(
        token: str, owner: str, repo: str, pr_number: int
    ) -> list[ChangedFile]:
        ...

    @staticmethod
    @abstractmethod
    async def get_file_content(
        token: str, owner: str, repo: str, path: str, ref: str
    ) -> str:
        ...

    @staticmethod
    @abstractmethod
    async def search_code(
        token: str, owner: str, repo: str, query: str, *, limit: int = 5
    ) -> list[CodeSearchHit]:
        ...
