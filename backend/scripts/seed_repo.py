from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Repository
from app.db.session import SessionLocal


async def seed(
    provider: str,
    owner: str,
    name: str,
    webhook_secret: str,
) -> None:
    async with SessionLocal() as session:
        stmt = pg_insert(Repository).values(
            provider=provider,
            owner=owner,
            name=name,
            webhook_secret=webhook_secret,
            ignore_globs=[],
            block_critical_merge=True,
            dialog_enabled=True,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["provider", "owner", "name"],
            set_={"webhook_secret": webhook_secret},
        )
        await session.execute(stmt)
        await session.commit()

        result = await session.execute(
            select(Repository).where(
                Repository.provider == provider,
                Repository.owner == owner,
                Repository.name == name,
            )
        )
        repo = result.scalar_one()
        print(
            f"seeded: id={repo.id} {repo.provider}:{repo.owner}/{repo.name} "
            f"webhook_secret={repo.webhook_secret}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="seed a Repository row for local testing")
    parser.add_argument("--provider", default="github", choices=["github", "gitlab"])
    parser.add_argument("--owner", default="acme")
    parser.add_argument("--name", default="widgets")
    parser.add_argument("--secret", default="topsecret")
    args = parser.parse_args()

    asyncio.run(seed(args.provider, args.owner, args.name, args.secret))


if __name__ == "__main__":
    main()
