from __future__ import annotations

import logging
from typing import ClassVar

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
    return {
        "provider": provider,
        "repository_id": repository_id,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "status": "received",
    }


class WorkerSettings:
    functions: ClassVar = [review_pull_request]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 600
