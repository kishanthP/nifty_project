"""Yahoo Finance (free, no account). Unofficial and may lag slightly — good as a fallback."""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote as url_quote

import httpx

from app.schemas.market import Candle, Quote
from app.services import market_hours
from app.services.market_data.base import Backoff, InstrumentRef, MarketDataProvider, ProviderError

logger = logging.getLogger(__name__)

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (share-market-app)", "Accept": "application/json"}


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self, poll_seconds: float = 5.0, client: httpx.AsyncClient | None = None) -> None:
        self.poll_seconds = poll_seconds
        self._client = client or httpx.AsyncClient(timeout=10, headers=_HEADERS)

    async def _chart(self, symbol: str) -> dict[str, Any]:
        url = _CHART_URL.format(symbol=url_quote(symbol, safe=""))
        try:
            response = await self._client.get(url, params={"interval": "1m", "range": "1d"})
            response.raise_for_status()
            result = response.json()["chart"]["result"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ProviderError(f"Yahoo request failed for {symbol}: {exc}") from exc
        if not result:
            raise ProviderError(f"Yahoo returned no data for {symbol}")
        return result[0]

    def _quote(self, instrument: InstrumentRef, chart: dict[str, Any]) -> Quote:
        meta = chart["meta"]
        opens = (chart.get("indicators", {}).get("quote") or [{}])[0].get("open") or []
        first_open = next((value for value in opens if value is not None), None)
        exchange_ts = (
            datetime.fromtimestamp(meta["regularMarketTime"], UTC)
            if meta.get("regularMarketTime")
            else None
        )
        return Quote(
            symbol=instrument.symbol,
            name=instrument.name,
            ltp=round(float(meta["regularMarketPrice"]), 2),
            open=round(first_open, 2) if first_open else None,
            high=meta.get("regularMarketDayHigh"),
            low=meta.get("regularMarketDayLow"),
            prev_close=meta.get("chartPreviousClose") or meta.get("previousClose"),
            exchange_ts=exchange_ts,
            received_at=datetime.now(UTC),
            source=self.name,
            market_status="open" if market_hours.is_market_open() else "closed",
        ).with_derived_change()

    async def stream(self, instruments: Sequence[InstrumentRef]) -> AsyncIterator[Quote]:
        tracked = [i for i in instruments if i.yahoo_symbol]
        backoff = Backoff(initial=self.poll_seconds, maximum=120)
        while True:
            try:
                for instrument in tracked:
                    chart = await self._chart(instrument.yahoo_symbol or "")
                    yield self._quote(instrument, chart)
                backoff.reset()
            except ProviderError as exc:
                logger.warning("%s", exc)
                await backoff.sleep()
                continue
            # Prices don't move when the market is closed, so poll rarely.
            await asyncio.sleep(self.poll_seconds if market_hours.is_market_open() else 300)

    async def fetch_intraday(self, instrument: InstrumentRef) -> list[Candle]:
        if not instrument.yahoo_symbol:
            return []
        chart = await self._chart(instrument.yahoo_symbol)
        timestamps = chart.get("timestamp") or []
        quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
        candles = []
        for index, ts in enumerate(timestamps):
            values = [
                quote.get(key, [None] * len(timestamps))[index]
                for key in ("open", "high", "low", "close")
            ]
            if any(value is None for value in values):
                continue
            o, h, l, c = (round(float(v), 2) for v in values)  # noqa: E741
            candles.append(Candle(time=int(ts), open=o, high=h, low=l, close=c))
        return candles

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["YahooProvider"]
