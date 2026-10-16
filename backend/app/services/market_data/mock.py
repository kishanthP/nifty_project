"""Fake prices for development: a random walk that ticks every second.

Lets you test alerts and notifications at any time, even when NSE is closed.
"""

import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.schemas.market import Candle, Quote
from app.services.market_data.base import InstrumentRef, MarketDataProvider

_HISTORY_MINUTES = 180


@dataclass
class _State:
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    candles: list[Candle] = field(default_factory=list)


class MockProvider(MarketDataProvider):
    name = "mock"

    def __init__(
        self,
        start_price: float = 22550.0,
        volatility: float = 3.0,
        tick_seconds: float = 1.0,
        seed: int | None = None,
    ) -> None:
        self.start_price = start_price
        self.volatility = volatility
        self.tick_seconds = tick_seconds
        self._rng = random.Random(seed)
        self._states: dict[str, _State] = {}

    def _state(self, instrument: InstrumentRef) -> _State:
        state = self._states.get(instrument.symbol)
        if state is None:
            state = self._backfill()
            self._states[instrument.symbol] = state
        return state

    def _backfill(self) -> _State:
        """Make up the last few hours of 1-minute candles, ending at the start price."""
        now_minute = int(datetime.now(UTC).timestamp()) // 60 * 60
        closes = [self.start_price]
        for _ in range(_HISTORY_MINUTES - 1):
            closes.append(closes[-1] - self._rng.gauss(0, self.volatility * 3))
        closes.reverse()
        candles = []
        previous = closes[0]
        for index, close in enumerate(closes):
            spread = abs(self._rng.gauss(0, self.volatility * 2))
            candles.append(
                Candle(
                    time=now_minute - (_HISTORY_MINUTES - 1 - index) * 60,
                    open=round(previous, 2),
                    high=round(max(previous, close) + spread, 2),
                    low=round(min(previous, close) - spread, 2),
                    close=round(close, 2),
                )
            )
            previous = close
        prices = [c.high for c in candles] + [c.low for c in candles]
        return _State(
            price=self.start_price,
            open=candles[0].open,
            high=max(prices),
            low=min(prices),
            prev_close=round(candles[0].open - self._rng.uniform(-60, 60), 2),
            candles=candles,
        )

    def _tick(self, instrument: InstrumentRef) -> Quote:
        state = self._state(instrument)
        state.price = round(state.price + self._rng.gauss(0, self.volatility), 2)
        state.high = max(state.high, state.price)
        state.low = min(state.low, state.price)
        now = datetime.now(UTC)
        self._update_candle(state, now)
        return Quote(
            symbol=instrument.symbol,
            name=instrument.name,
            ltp=state.price,
            open=state.open,
            high=state.high,
            low=state.low,
            prev_close=state.prev_close,
            exchange_ts=now,
            received_at=now,
            source=self.name,
            market_status="open",
        ).with_derived_change()

    @staticmethod
    def _update_candle(state: _State, now: datetime) -> None:
        minute = int(now.timestamp()) // 60 * 60
        last = state.candles[-1] if state.candles else None
        if last and last.time == minute:
            last.high = max(last.high, state.price)
            last.low = min(last.low, state.price)
            last.close = state.price
        else:
            state.candles.append(
                Candle(
                    time=minute,
                    open=state.price,
                    high=state.price,
                    low=state.price,
                    close=state.price,
                )
            )
            del state.candles[:-_HISTORY_MINUTES]

    async def stream(self, instruments: Sequence[InstrumentRef]) -> AsyncIterator[Quote]:
        while True:
            for instrument in instruments:
                yield self._tick(instrument)
            await asyncio.sleep(self.tick_seconds)

    async def fetch_intraday(self, instrument: InstrumentRef) -> list[Candle]:
        return [candle.model_copy() for candle in self._state(instrument).candles]
