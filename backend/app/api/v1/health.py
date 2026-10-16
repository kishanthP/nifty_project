import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import AppSettings, Cache, DbSession
from app.services import market_hours

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health/live")
async def live() -> dict[str, str]:
    """The process is up (used by Docker's health check)."""
    return {"status": "ok"}


@router.get("/health")
async def health(db: DbSession, cache: Cache, settings: AppSettings) -> dict[str, Any]:
    """Database, Redis and live-feed status in one place."""
    checks: dict[str, Any] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Health: database check failed: %s", exc)
        checks["database"] = "down"
    try:
        await cache.redis.ping()
        checks["redis"] = "ok"
        heartbeat = await cache.get_heartbeat()
    except Exception as exc:
        logger.warning("Health: redis check failed: %s", exc)
        checks["redis"] = "down"
        heartbeat = None

    feed: dict[str, Any] = {"status": "down", "provider": settings.market_data_provider}
    if heartbeat:
        last_tick = heartbeat.get("last_tick_at")
        age = (
            (datetime.now(UTC) - datetime.fromisoformat(last_tick)).total_seconds()
            if last_tick
            else None
        )
        always_open = heartbeat.get("provider") == "mock"
        if not always_open and not market_hours.is_market_open():
            status = "closed"
        elif age is not None and age <= settings.feed_stale_after_seconds:
            status = "live"
        else:
            status = "stale"
        feed = {
            "status": status,
            "provider": heartbeat.get("provider"),
            "last_tick_age_seconds": round(age, 1) if age is not None else None,
        }
    checks["feed"] = feed

    healthy = checks["database"] == "ok" and checks["redis"] == "ok"
    return {"status": "ok" if healthy else "degraded", **checks}
