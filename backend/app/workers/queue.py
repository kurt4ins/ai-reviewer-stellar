from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_redis_pool() -> ArqRedis:
    return await create_pool(redis_settings())


REVIEW_TASK = "review_pull_request"
