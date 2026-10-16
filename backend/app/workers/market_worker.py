"""The market worker: receives prices, stores them in Redis and checks alerts.

Run with:  python -m app.workers.market_worker

It runs four jobs side by side:
  1. feed       — provider ticks → Redis (latest price + live channel) → alert engine
  2. candles    — refreshes the intraday chart data every minute
  3. retries    — re-sends notifications that failed temporarily
  4. lock       — keeps our "I'm the active worker" lock alive in Redis
"""

import asyncio
import contextlib
import logging
import signal
import socket
import time
import uuid
from datetime import datetime

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal, engine
from app.models import Instrument
from app.schemas.market import Quote
from app.services import market_hours
from app.services.alert_engine import AlertEngine
from app.services.market_data import InstrumentRef, MarketDataProvider, build_provider
from app.services.notifier import build_notifier
from app.services.price_cache import WORKER_LOCK_KEY, PriceCache, create_redis
from app.services.redis_lock import RedisLock

logger = logging.getLogger("market_worker")


async def load_instruments() -> list[InstrumentRef]:
    async with SessionLocal() as session:
        rows = await session.scalars(select(Instrument).where(Instrument.is_active))
        return [
            InstrumentRef(
                id=row.id,
                symbol=row.symbol,
                name=row.name,
                angelone_exchange_type=row.angelone_exchange_type,
                angelone_token=row.angelone_token,
                yahoo_symbol=row.yahoo_symbol,
            )
            for row in rows
        ]


class MarketWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        self.redis = create_redis(settings.redis_url)
        self.cache = PriceCache(self.redis)
        self.lock = RedisLock(self.redis, WORKER_LOCK_KEY, owner=self.worker_id)
        self.notifier = build_notifier()
        self.engine = AlertEngine(
            SessionLocal,
            self.notifier,
            self.cache,
            check_interval=settings.alert_eval_interval_seconds,
            max_attempts=settings.notification_max_attempts,
            expiry_minutes=settings.notification_expiry_minutes,
            frontend_url=settings.frontend_url,
        )
        self.provider: MarketDataProvider | None = None
        self.instruments: list[InstrumentRef] = []
        self.last_tick_at: datetime | None = None
        self.last_source: str | None = None
        self._last_published: dict[str, float] = {}

    async def run(self) -> None:
        await self.lock.acquire()
        try:
            self.instruments = await load_instruments()
            if not self.instruments:
                raise RuntimeError("No active instruments in the database. Did migrations run?")
            self.provider = build_provider(self.settings)
            logger.info(
                "Worker %s started: provider=%s notifier=%s instruments=%s",
                self.worker_id,
                self.provider.name,
                self.notifier.channel,
                ", ".join(i.symbol for i in self.instruments),
            )
            async with asyncio.TaskGroup() as group:
                group.create_task(self.lock.keep_alive())
                group.create_task(self._feed())
                group.create_task(self._candles())
                group.create_task(self._retries())
                group.create_task(self._heartbeat())
        finally:
            await self.engine.drain()
            if self.provider is not None:
                await self.provider.aclose()
            with contextlib.suppress(Exception):
                await self.lock.release()
            await self.redis.aclose()
            await engine.dispose()

    # --- jobs ---
    async def _feed(self) -> None:
        assert self.provider is not None
        by_symbol = {i.symbol: i for i in self.instruments}
        async for quote in self.provider.stream(self.instruments):
            instrument = by_symbol.get(quote.symbol)
            if instrument is None:
                continue
            self.last_tick_at = quote.received_at
            self.last_source = quote.source
            await self._publish(quote)
            try:
                await self.engine.on_quote(instrument.id, quote)
            except Exception:
                # A database hiccup must not stop the price feed; the next tick retries.
                logger.exception("Alert check failed for %s", quote.symbol)

    async def _publish(self, quote: Quote) -> None:
        """Store + broadcast, at most every `quote_publish_interval_seconds` per symbol."""
        now = time.monotonic()
        if (
            now - self._last_published.get(quote.symbol, 0.0)
            < self.settings.quote_publish_interval_seconds
        ):
            return
        self._last_published[quote.symbol] = now
        try:
            await self.cache.set_quote(quote)
        except Exception:
            logger.exception("Could not publish quote to Redis")

    async def _candles(self) -> None:
        assert self.provider is not None
        while True:
            for instrument in self.instruments:
                try:
                    candles = await self.provider.fetch_intraday(instrument)
                    if candles:
                        await self.cache.set_candles(instrument.symbol, candles, ttl_seconds=86400)
                except Exception as exc:
                    logger.warning("Candle refresh failed for %s: %s", instrument.symbol, exc)
            live = self.provider.name == "mock" or market_hours.is_market_open()
            await asyncio.sleep(60 if live else 900)

    async def _retries(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self.engine.retry_pending()
            except Exception:
                logger.exception("Notification retry failed")

    async def _heartbeat(self) -> None:
        assert self.provider is not None
        while True:
            try:
                await self.cache.heartbeat(
                    self.last_source or self.provider.name, self.worker_id, self.last_tick_at
                )
            except Exception as exc:
                logger.warning("Heartbeat failed: %s", exc)
            await asyncio.sleep(10)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    worker = MarketWorker(settings)
    task = asyncio.create_task(worker.run())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # not available on Windows
            loop.add_signal_handler(sig, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
