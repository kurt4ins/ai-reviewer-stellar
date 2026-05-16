from __future__ import annotations

import secrets
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Repository, User
from app.db.session import get_db
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/repos", tags=["repos"])

Provider = Literal["github", "gitlab"]


class RepoCreate(BaseModel):
    provider: Provider
    owner: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)


class RepoUpdate(BaseModel):
    ignore_globs: list[str] | None = None
    block_critical_merge: bool | None = None
    dialog_enabled: bool | None = None


class RepoResponse(BaseModel):
    id: uuid.UUID
    provider: str
    owner: str
    name: str
    webhook_secret: str
    webhook_url: str
    ignore_globs: list[str]
    block_critical_merge: bool
    dialog_enabled: bool


def _webhook_url(provider: str) -> str:
    base = get_settings().webhook_base_url.rstrip("/")
    return f"{base}/webhook/{provider}"


def _to_response(repo: Repository) -> RepoResponse:
    return RepoResponse(
        id=repo.id,
        provider=repo.provider,
        owner=repo.owner,
        name=repo.name,
        webhook_secret=repo.webhook_secret,
        webhook_url=_webhook_url(repo.provider),
        ignore_globs=repo.ignore_globs,
        block_critical_merge=repo.block_critical_merge,
        dialog_enabled=repo.dialog_enabled,
    )


async def _owned_repo(
    repo_id: uuid.UUID, user: User, session: AsyncSession
) -> Repository:
    repo = await session.get(Repository, repo_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return repo


@router.post("", response_model=RepoResponse, status_code=201)
async def create_repo(
    body: RepoCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RepoResponse:
    repo = Repository(
        user_id=user.id,
        provider=body.provider,
        owner=body.owner,
        name=body.name,
        webhook_secret=secrets.token_urlsafe(32),
        ignore_globs=[],
        block_critical_merge=True,
        dialog_enabled=True,
    )
    session.add(repo)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="repository already registered",
        ) from exc
    await session.refresh(repo)
    return _to_response(repo)


@router.get("", response_model=list[RepoResponse])
async def list_repos(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RepoResponse]:
    result = await session.execute(
        select(Repository)
        .where(Repository.user_id == user.id)
        .order_by(Repository.created_at.desc())
    )
    return [_to_response(r) for r in result.scalars().all()]


@router.get("/{repo_id}", response_model=RepoResponse)
async def get_repo(
    repo_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RepoResponse:
    return _to_response(await _owned_repo(repo_id, user, session))


@router.patch("/{repo_id}", response_model=RepoResponse)
async def update_repo(
    repo_id: uuid.UUID,
    body: RepoUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RepoResponse:
    repo = await _owned_repo(repo_id, user, session)
    if body.ignore_globs is not None:
        repo.ignore_globs = body.ignore_globs
    if body.block_critical_merge is not None:
        repo.block_critical_merge = body.block_critical_merge
    if body.dialog_enabled is not None:
        repo.dialog_enabled = body.dialog_enabled
    await session.commit()
    await session.refresh(repo)
    return _to_response(repo)


@router.delete("/{repo_id}", status_code=204)
async def delete_repo(
    repo_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    repo = await _owned_repo(repo_id, user, session)
    await session.delete(repo)
    await session.commit()
