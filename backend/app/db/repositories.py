from __future__ import annotations

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
