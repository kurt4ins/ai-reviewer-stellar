from __future__ import annotations

import logging
from typing import ClassVar

from app.config import get_settings
from app.db.models import Review
from app.db.repositories import get_repository_by_id
from app.db.reviews import create_review, finalize_review, mark_review_failed
from app.db.session import SessionLocal
from app.llm.pipeline import AnalyzedFinding, analyze_pull_request_hunk
from app.llm.tools import ToolContext
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
    settings = get_settings()

    async with SessionLocal() as session:
        repo = await get_repository_by_id(session, repository_id)
        if repo is None:
            logger.error("repository %s not found, skipping job", repository_id)
            return {"status": "repository_not_found", "repository_id": repository_id}
        owner = repo.owner
        name = repo.name
        token = decrypt_token(repo.encrypted_token)
        review = await create_review(
            session,
            repository_id=repo.id,
            pr_number=pr_number,
            commit_sha=commit_sha,
        )
        review_id = review.id
        await session.commit()

    provider_cls = get_provider(provider)
    try:
        changed_files = await provider_cls.get_pr_diff(token, owner, name, pr_number)
    except Exception as exc:
        logger.exception("failed to fetch diff: %s", exc)
        async with SessionLocal() as session:
            failed = await session.get(Review, review_id)
            if failed is not None:
                await mark_review_failed(session, review=failed)
                await session.commit()
        return {"status": "diff_fetch_failed", "review_id": str(review_id)}

    tool_context = ToolContext(
        provider_cls=provider_cls,
        token=token,
        owner=owner,
        repo=name,
        commit_sha=commit_sha,
    )

    all_findings: list[AnalyzedFinding] = []
    hunk_count = 0
    skipped_files = 0
    skipped_hunks = 0

    for changed in changed_files:
        if changed.patch is None:
            skipped_files += 1
            logger.info("skipping file without patch: %s", changed.path)
            continue
        hunks = parse_patch(changed.path, changed.patch)
        for hunk in hunks:
            hunk_count += 1
            try:
                analysis = await analyze_pull_request_hunk(
                    classifier_model=settings.default_classifier_model,
                    analyzer_model=settings.default_analyzer_model,
                    file_path=changed.path,
                    hunk=hunk,
                    tool_context=tool_context,
                )
            except Exception as exc:
                skipped_hunks += 1
                logger.exception(
                    "analysis failed for %s lines=%s-%s: %s",
                    changed.path,
                    hunk.new_start,
                    hunk.new_end,
                    exc,
                )
                continue
            if analysis.skipped_reason:
                logger.info(
                    "hunk skipped file=%s lines=%s-%s reason=%s",
                    changed.path,
                    hunk.new_start,
                    hunk.new_end,
                    analysis.skipped_reason,
                )
                continue
            all_findings.extend(analysis.findings)

    async with SessionLocal() as session:
        final_review = await session.get(Review, review_id)
        if final_review is None:
            logger.error("review %s vanished before finalize", review_id)
            return {"status": "review_missing", "review_id": str(review_id)}
        await finalize_review(session, review=final_review, findings=all_findings)
        await session.commit()

    logger.info(
        "review finished provider=%s repo=%s/%s pr=%s files=%s hunks=%s "
        "findings=%s skipped_files=%s skipped_hunks=%s",
        provider,
        owner,
        name,
        pr_number,
        len(changed_files),
        hunk_count,
        len(all_findings),
        skipped_files,
        skipped_hunks,
    )

    return {
        "status": "completed",
        "review_id": str(review_id),
        "provider": provider,
        "repository_id": repository_id,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "files": len(changed_files),
        "hunks": hunk_count,
        "findings": len(all_findings),
        "skipped_files": skipped_files,
        "skipped_hunks": skipped_hunks,
    }


class WorkerSettings:
    functions: ClassVar = [review_pull_request]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 600
