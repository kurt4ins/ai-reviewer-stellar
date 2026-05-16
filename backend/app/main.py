from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, repos, reviews, webhooks
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

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhooks.router)
    app.include_router(auth.router)
    app.include_router(repos.router)
    app.include_router(reviews.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
