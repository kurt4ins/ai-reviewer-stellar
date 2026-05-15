from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import webhooks
from app.config import get_settings
from app.workers.queue import get_redis_pool

logger = logging.getLogger("stellar")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app.state.redis = await get_redis_pool()
    logger.info("stellar backend startup complete")
    try:
        yield
    finally:
        await app.state.redis.aclose()
        logger.info("stellar backend shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title="Stellar API", version="0.1.0", lifespan=lifespan)
    app.include_router(webhooks.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
