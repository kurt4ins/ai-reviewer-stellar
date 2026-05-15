from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Repository


async def get_repository(
    session: AsyncSession, provider: str, owner: str, name: str
) -> Repository | None:
    stmt = select(Repository).where(
        Repository.provider == provider,
        Repository.owner == owner,
        Repository.name == name,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_repository_by_id(
    session: AsyncSession, repository_id: str | uuid.UUID
) -> Repository | None:
    if isinstance(repository_id, str):
        repository_id = uuid.UUID(repository_id)
    return await session.get(Repository, repository_id)
