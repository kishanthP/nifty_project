"""The contract every market-data source follows.

To add a new broker (Upstox, Zerodha, ...), write one class that implements
`stream()` and `fetch_intraday()` and register it in factory.py.
"""

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.schemas.market import Candle, Quote


class ProviderError(Exception):
    """A temporary problem (network, rate limit). The provider retries by itself."""


class ProviderAuthError(ProviderError):
    """Login failed or the session expired."""


class ProviderConfigError(ProviderError):
    """Missing or invalid settings — retrying won't help."""


@dataclass(frozen=True)
class InstrumentRef:
    id: int
    symbol: str
    name: str
    angelone_exchange_type: int | None = None
    angelone_token: str | None = None
    yahoo_symbol: str | None = None


class MarketDataProvider(ABC):
    name: ClassVar[str]

    @abstractmethod
    def stream(self, instruments: Sequence[InstrumentRef]) -> AsyncIterator[Quote]:
        """Yield quotes forever, reconnecting on errors internally."""

    @abstractmethod
    async def fetch_intraday(self, instrument: InstrumentRef) -> list[Candle]:
        """1-minute candles for the latest trading session."""

    async def aclose(self) -> None:  # noqa: B027  (optional hook)
        """Release network resources."""


class Backoff:
    """Exponential backoff with jitter: 1s, 2s, 4s, ... capped at `maximum`."""

    def __init__(self, initial: float = 1.0, maximum: float = 300.0) -> None:
        self.initial = initial
        self.maximum = maximum
        self.attempt = 0

    def reset(self) -> None:
        self.attempt = 0

    def next_delay(self) -> float:
        delay = min(self.maximum, self.initial * 2**self.attempt)
        self.attempt += 1
        return delay * random.uniform(0.8, 1.2)

    async def sleep(self) -> None:
        await asyncio.sleep(self.next_delay())
