from __future__ import annotations

import logging
from typing import ClassVar

from app.db.repositories import get_repository_by_id
from app.db.session import SessionLocal
from app.providers import get_provider
from app.security.crypto import decrypt_token
from app.utils.diff_parser import parse_patch
from app.workers.queue import redis_settings as _redis_settings

logger = logging.getLogger("stellar.worker")


async def review_pull_request(
    ctx: dict,
    provider: str,
    repository_id: str,
    pr_number: int,
    commit_sha: str,
) -> dict:
    logger.info(
        "received review job provider=%s repo=%s pr=%s sha=%s",
        provider,
        repository_id,
        pr_number,
        commit_sha,
    )

    async with SessionLocal() as session:
        repo = await get_repository_by_id(session, repository_id)
        if repo is None:
            logger.error("repository %s not found, skipping job", repository_id)
            return {"status": "repository_not_found", "repository_id": repository_id}
        owner = repo.owner
        name = repo.name
        token = decrypt_token(repo.encrypted_token)

    provider_cls = get_provider(provider)
    changed_files = await provider_cls.get_pr_diff(token, owner, name, pr_number)

    hunk_count = 0
    skipped = 0
    for changed in changed_files:
        if changed.patch is None:
            skipped += 1
            logger.info("skipping file without patch: %s", changed.path)
            continue
        hunks = parse_patch(changed.path, changed.patch)
        for hunk in hunks:
            hunk_count += 1
            logger.info(
                "Sending hunk to LLM: file=%s lines=%s-%s",
                changed.path,
                hunk.new_start,
                hunk.new_end,
            )

    logger.info(
        "diff extracted provider=%s repo=%s/%s pr=%s files=%s hunks=%s skipped=%s",
        provider,
        owner,
        name,
        pr_number,
        len(changed_files),
        hunk_count,
        skipped,
    )

    return {
        "provider": provider,
        "repository_id": repository_id,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "files": len(changed_files),
        "hunks": hunk_count,
        "skipped": skipped,
        "status": "diff_extracted",
    }


class WorkerSettings:
    functions: ClassVar = [review_pull_request]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 600
