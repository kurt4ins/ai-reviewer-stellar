from __future__ import annotations

import hashlib
import hmac

import pytest

from app.providers.base import SignatureError
from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider


def _gh_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_valid_signature_passes():
    secret = "topsecret"
    body = b'{"action": "opened"}'
    headers = {"x-hub-signature-256": _gh_sig(secret, body)}
    GitHubProvider.verify_signature(secret, body, headers)


def test_github_invalid_signature_rejected():
    secret = "topsecret"
    body = b'{"action": "opened"}'
    headers = {"x-hub-signature-256": _gh_sig("wrong", body)}
    with pytest.raises(SignatureError):
        GitHubProvider.verify_signature(secret, body, headers)


def test_github_missing_header_rejected():
    with pytest.raises(SignatureError):
        GitHubProvider.verify_signature("s", b"{}", {})


def test_github_malformed_header_rejected():
    with pytest.raises(SignatureError):
        GitHubProvider.verify_signature("s", b"{}", {"x-hub-signature-256": "abcdef"})


def test_gitlab_valid_token_passes():
    GitLabProvider.verify_signature("topsecret", b"{}", {"x-gitlab-token": "topsecret"})


def test_gitlab_invalid_token_rejected():
    with pytest.raises(SignatureError):
        GitLabProvider.verify_signature("topsecret", b"{}", {"x-gitlab-token": "wrong"})


def test_gitlab_missing_token_rejected():
    with pytest.raises(SignatureError):
        GitLabProvider.verify_signature("topsecret", b"{}", {})
