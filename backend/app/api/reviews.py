from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Finding, Repository, Review, User
from app.db.session import get_db
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class ReviewSummary(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    repo_full_name: str
    provider: str
    pr_number: int
    commit_sha: str
    status: str
    findings_count: int
    critical_count: int
    created_at: datetime


class FindingItem(BaseModel):
    id: uuid.UUID
    file_path: str
    line_number: int
    cwe: str
    severity: str
    description: str
    fix_code: str | None
    fix_explanation: str | None
    confidence: float


class ReviewDetail(ReviewSummary):
    findings: list[FindingItem]


def _summary(review: Review, repo: Repository) -> ReviewSummary:
    return ReviewSummary(
        id=review.id,
        repository_id=review.repository_id,
        repo_full_name=repo.full_name,
        provider=repo.provider,
        pr_number=review.pr_number,
        commit_sha=review.commit_sha,
        status=review.status,
        findings_count=review.findings_count,
        critical_count=review.critical_count,
        created_at=review.created_at,
    )


@router.get("", response_model=list[ReviewSummary])
async def list_reviews(
    repo_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ReviewSummary]:
    stmt = (
        select(Review, Repository)
        .join(Repository, Repository.id == Review.repository_id)
        .where(Repository.user_id == user.id)
        .order_by(Review.created_at.desc())
    )
    if repo_id is not None:
        stmt = stmt.where(Repository.id == repo_id)
    result = await session.execute(stmt)
    return [_summary(review, repo) for review, repo in result.all()]


@router.get("/{review_id}", response_model=ReviewDetail)
async def get_review(
    review_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReviewDetail:
    result = await session.execute(
        select(Review, Repository)
        .join(Repository, Repository.id == Review.repository_id)
        .where(Review.id == review_id, Repository.user_id == user.id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="review not found"
        )
    review, repo = row
    findings_result = await session.execute(
        select(Finding)
        .where(Finding.review_id == review.id)
        .order_by(Finding.file_path, Finding.line_number)
    )
    findings = [
        FindingItem(
            id=f.id,
            file_path=f.file_path,
            line_number=f.line_number,
            cwe=f.cwe,
            severity=f.severity,
            description=f.description,
            fix_code=f.fix_code,
            fix_explanation=f.fix_explanation,
            confidence=f.confidence,
        )
        for f in findings_result.scalars().all()
    ]
    return ReviewDetail(**_summary(review, repo).model_dump(), findings=findings)
