from __future__ import annotations

import argparse
import hashlib
import hmac
import json

import httpx


def build_github_payload(owner: str, name: str, pr: int, sha: str) -> dict:
    return {
        "action": "opened",
        "pull_request": {"number": pr, "head": {"sha": sha}},
        "repository": {"full_name": f"{owner}/{name}"},
    }


def build_gitlab_payload(owner: str, name: str, pr: int, sha: str) -> dict:
    return {
        "object_kind": "merge_request",
        "object_attributes": {
            "action": "open",
            "iid": pr,
            "last_commit": {"id": sha},
        },
        "project": {"path_with_namespace": f"{owner}/{name}"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="send a signed test webhook")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--provider", default="github", choices=["github", "gitlab"])
    parser.add_argument("--secret", default="testsecret")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()

    if args.provider == "github":
        payload = build_github_payload(args.owner, args.name, args.pr, args.sha)
        body = json.dumps(payload).encode("utf-8")
        signature = "sha256=" + hmac.new(
            args.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        }
        endpoint = f"{args.url}/webhook/github"
    else:
        payload = build_gitlab_payload(args.owner, args.name, args.pr, args.sha)
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "X-Gitlab-Event": "Merge Request Hook",
            "X-Gitlab-Token": args.secret,
            "Content-Type": "application/json",
        }
        endpoint = f"{args.url}/webhook/gitlab"

    resp = httpx.post(endpoint, content=body, headers=headers, timeout=10.0)
    print(f"{resp.status_code} {resp.text}")


if __name__ == "__main__":
    main()
