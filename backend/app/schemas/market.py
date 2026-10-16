from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Quote(BaseModel):
    """Latest price snapshot for one instrument. Shared by the worker, Redis and the API."""

    symbol: str
    name: str
    ltp: float  # last traded price
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    exchange_ts: datetime | None = None  # time the exchange stamped this price
    received_at: datetime  # time our worker received it
    source: str  # provider name: angelone | yahoo | mock
    market_status: Literal["open", "closed"]

    def with_derived_change(self) -> "Quote":
        """Fill change / change_pct from prev_close when the provider didn't send them."""
        if self.prev_close and self.change is None:
            change = round(self.ltp - self.prev_close, 2)
            return self.model_copy(
                update={
                    "change": change,
                    "change_pct": round(change / self.prev_close * 100, 2),
                }
            )
        return self


class Candle(BaseModel):
    time: int  # candle start, Unix seconds (UTC)
    open: float
    high: float
    low: float
    close: float


class MarketStatusOut(BaseModel):
    is_open: bool
    reason: str
    holiday_name: str | None
    next_open: datetime


class InstrumentOut(BaseModel):
    symbol: str
    name: str
    exchange: str
    instrument_type: str

    model_config = {"from_attributes": True}
