"""Redis helpers: latest quotes, intraday candles, live channels and worker heartbeat.

Redis is the fast "shared memory" between the market worker and every API instance.
"""

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.schemas.market import Candle, Quote

QUOTE_KEY = "quote:{symbol}"
CANDLES_KEY = "candles:{symbol}:1m"
QUOTES_CHANNEL = "channel:quotes"
ALERTS_CHANNEL = "channel:alerts"
HEARTBEAT_KEY = "worker:heartbeat"
WORKER_LOCK_KEY = "worker:market-feed:lock"


def create_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True, health_check_interval=30)


class PriceCache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    # --- Quotes ---
    async def set_quote(self, quote: Quote) -> None:
        payload = quote.model_dump_json()
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.set(QUOTE_KEY.format(symbol=quote.symbol), payload)
            pipe.publish(QUOTES_CHANNEL, payload)
            await pipe.execute()

    async def get_quote(self, symbol: str) -> Quote | None:
        raw = await self.redis.get(QUOTE_KEY.format(symbol=symbol))
        return Quote.model_validate_json(raw) if raw else None

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not symbols:
            return []
        raws = await self.redis.mget([QUOTE_KEY.format(symbol=s) for s in symbols])
        return [Quote.model_validate_json(raw) for raw in raws if raw]

    # --- Candles ---
    async def set_candles(self, symbol: str, candles: list[Candle], ttl_seconds: int) -> None:
        payload = json.dumps([c.model_dump() for c in candles])
        await self.redis.set(CANDLES_KEY.format(symbol=symbol), payload, ex=ttl_seconds)

    async def get_candles(self, symbol: str) -> list[Candle]:
        raw = await self.redis.get(CANDLES_KEY.format(symbol=symbol))
        return [Candle.model_validate(item) for item in json.loads(raw)] if raw else []

    # --- Alert events (for instant in-app toasts) ---
    async def publish_alert_event(self, event: dict[str, Any]) -> None:
        await self.redis.publish(ALERTS_CHANNEL, json.dumps(event, default=str))

    # --- Worker heartbeat (feeds /health) ---
    async def heartbeat(
        self, provider: str, worker_id: str, last_tick_at: datetime | None, ttl_seconds: int = 60
    ) -> None:
        payload = {
            "provider": provider,
            "worker_id": worker_id,
            "last_tick_at": last_tick_at.isoformat() if last_tick_at else None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await self.redis.set(HEARTBEAT_KEY, json.dumps(payload), ex=ttl_seconds)

    async def get_heartbeat(self) -> dict[str, Any] | None:
        raw = await self.redis.get(HEARTBEAT_KEY)
        return json.loads(raw) if raw else None
