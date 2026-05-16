from __future__ import annotations

import json
import logging
from typing import Any

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import get_repository
from app.db.session import get_db
from app.providers.base import GitProvider, SignatureError
from app.providers.github import GitHubProvider
from app.providers.gitlab import GitLabProvider
from app.workers.queue import REVIEW_TASK

logger = logging.getLogger("stellar.webhook")

router = APIRouter(prefix="/webhook", tags=["webhooks"])


def _get_arq(request: Request) -> ArqRedis:
    pool = getattr(request.app.state, "redis", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="queue not initialized")
    return pool


async def _handle(
    provider: type[GitProvider],
    request: Request,
    session: AsyncSession,
    arq: ArqRedis,
) -> dict[str, Any]:
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc

    event = provider.parse_event(headers, payload)
    if event is None:
        return {"status": "ignored"}

    repo = await get_repository(session, event.provider, event.owner, event.repo)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"repository {event.owner}/{event.repo} is not registered",
        )

    try:
        provider.verify_signature(repo.webhook_secret, raw_body, headers)
    except SignatureError as exc:
        logger.warning(
            "signature rejected provider=%s repo=%s reason=%s",
            event.provider,
            repo.full_name,
            exc,
        )
        raise HTTPException(status_code=401, detail="invalid signature") from exc

    job = await arq.enqueue_job(
        REVIEW_TASK,
        event.provider,
        str(repo.id),
        event.pr_number,
        event.commit_sha,
        _job_id=f"{event.provider}:{repo.id}:{event.pr_number}:{event.commit_sha}",
    )

    logger.info(
        "enqueued review provider=%s repo=%s pr=%s sha=%s job_id=%s",
        event.provider,
        repo.full_name,
        event.pr_number,
        event.commit_sha,
        getattr(job, "job_id", None),
    )

    return {
        "status": "queued",
        "job_id": getattr(job, "job_id", None),
        "provider": event.provider,
        "repository": repo.full_name,
        "pr_number": event.pr_number,
        "commit_sha": event.commit_sha,
    }


@router.post("/github", status_code=200)
async def github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    arq: ArqRedis = Depends(_get_arq),
) -> dict[str, Any]:
    return await _handle(GitHubProvider, request, session, arq)


@router.post("/gitlab", status_code=200)
async def gitlab_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    arq: ArqRedis = Depends(_get_arq),
) -> dict[str, Any]:
    return await _handle(GitLabProvider, request, session, arq)
