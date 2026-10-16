"""Use the main provider; if it goes quiet during market hours, switch to a backup.

Example: MARKET_DATA_PROVIDER=angelone, FALLBACK_PROVIDER=yahoo. If Angel One sends
nothing for FALLBACK_AFTER_SECONDS while NSE is open, Yahoo prices are used until
Angel One recovers.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Sequence

from app.schemas.market import Candle, Quote
from app.services import market_hours
from app.services.market_data.base import InstrumentRef, MarketDataProvider, ProviderError

logger = logging.getLogger(__name__)

_RECOVERED_WITHIN = 5.0


class FailoverProvider(MarketDataProvider):
    name = "failover"

    def __init__(
        self, primary: MarketDataProvider, backup: MarketDataProvider, after_seconds: float
    ) -> None:
        self.primary = primary
        self.backup = backup
        self.after_seconds = after_seconds

    async def stream(self, instruments: Sequence[InstrumentRef]) -> AsyncIterator[Quote]:
        queue: asyncio.Queue[Quote] = asyncio.Queue(maxsize=1000)
        last_primary = time.monotonic()

        async def pump(provider: MarketDataProvider, is_primary: bool) -> None:
            nonlocal last_primary
            async for quote in provider.stream(instruments):
                if is_primary:
                    last_primary = time.monotonic()
                await queue.put(quote)

        primary_task: asyncio.Task | None = asyncio.create_task(pump(self.primary, True))
        backup_task: asyncio.Task | None = None
        try:
            while True:
                try:
                    quote: Quote | None = await asyncio.wait_for(queue.get(), timeout=5)
                except TimeoutError:
                    quote = None

                if primary_task is not None and primary_task.done():
                    exc = primary_task.exception()
                    logger.error("Primary provider %s stopped: %s", self.primary.name, exc)
                    primary_task = None  # stay on the backup from now on

                quiet_for = time.monotonic() - last_primary
                primary_down = primary_task is None or (
                    market_hours.is_market_open() and quiet_for > self.after_seconds
                )
                if primary_down and backup_task is None:
                    logger.warning("Switching to backup provider %s", self.backup.name)
                    backup_task = asyncio.create_task(pump(self.backup, False))
                elif not primary_down and backup_task is not None and quiet_for < _RECOVERED_WITHIN:
                    logger.info("Primary provider %s recovered", self.primary.name)
                    backup_task.cancel()
                    backup_task = None

                if quote is None:
                    continue
                if quote.source == self.backup.name and backup_task is None:
                    continue  # leftover backup quote after recovery
                yield quote
        finally:
            for task in (primary_task, backup_task):
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

    async def fetch_intraday(self, instrument: InstrumentRef) -> list[Candle]:
        try:
            return await self.primary.fetch_intraday(instrument)
        except ProviderError as exc:
            logger.warning("Primary candles failed (%s); using backup", exc)
            return await self.backup.fetch_intraday(instrument)

    async def aclose(self) -> None:
        await self.primary.aclose()
        await self.backup.aclose()
