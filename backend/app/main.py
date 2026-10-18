import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.services.notifier import Notifier, build_notifier
from app.services.price_cache import PriceCache, create_redis
from app.services.realtime import RealtimeHub


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    redis: Redis | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    """Build the API. Tests pass their own database, Redis and notifier."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from app.db import session as db_session

        app.state.session_factory = session_factory or db_session.SessionLocal
        app.state.redis = redis or create_redis(settings.redis_url)
        app.state.cache = PriceCache(app.state.redis)
        app.state.notifier = notifier or build_notifier()
        app.state.hub = RealtimeHub(app.state.redis)
        await app.state.hub.start()

        worker_task: asyncio.Task | None = None
        if settings.run_worker_in_api:
            from app.workers.market_worker import run_embedded

            worker_task = asyncio.create_task(run_embedded(settings), name="market-worker")
        yield
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
        await app.state.hub.stop()
        if redis is None:
            await app.state.redis.aclose()
        if session_factory is None:
            await db_session.engine.dispose()

    app = FastAPI(
        title="Share Market API",
        version="0.1.0",
        description="Live Indian market data (NIFTY 50) with price alerts.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
