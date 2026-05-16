from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Finding, Review
from app.llm.pipeline import AnalyzedFinding


async def create_review(
    session: AsyncSession,
    *,
    repository_id: uuid.UUID,
    pr_number: int,
    commit_sha: str,
) -> Review:
    review = Review(
        repository_id=repository_id,
        pr_number=pr_number,
        commit_sha=commit_sha,
        status="running",
    )
    session.add(review)
    await session.flush()
    return review


async def finalize_review(
    session: AsyncSession,
    *,
    review: Review,
    findings: Iterable[AnalyzedFinding],
    status: str = "completed",
) -> Review:
    findings_list = list(findings)
    for f in findings_list:
        session.add(
            Finding(
                review_id=review.id,
                file_path=f.file_path,
                line_number=f.line_number,
                cwe=f.cwe,
                severity=f.severity,
                description=f.description,
                fix_code=f.fix_code,
                fix_explanation=f.fix_explanation,
                confidence=f.confidence,
            )
        )
    review.findings_count = len(findings_list)
    review.critical_count = sum(1 for f in findings_list if f.severity == "critical")
    review.status = status
    await session.flush()
    return review


async def mark_review_failed(
    session: AsyncSession,
    *,
    review: Review,
) -> Review:
    review.status = "failed"
    await session.flush()
    return review
