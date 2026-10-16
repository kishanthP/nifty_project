from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import Cache, DbSession
from app.models import Instrument
from app.schemas.market import Candle, InstrumentOut, MarketStatusOut, Quote
from app.services import market_hours

router = APIRouter()


@router.get("/instruments", response_model=list[InstrumentOut])
async def instruments(db: DbSession) -> list[InstrumentOut]:
    rows = await db.scalars(select(Instrument).where(Instrument.is_active).order_by(Instrument.id))
    return [InstrumentOut.model_validate(row) for row in rows]


@router.get("/status", response_model=MarketStatusOut)
async def status() -> MarketStatusOut:
    """Is NSE open right now? (Based on the clock and the holiday list.)"""
    current = market_hours.market_status()
    return MarketStatusOut(
        is_open=current.is_open,
        reason=current.reason,
        holiday_name=current.holiday_name,
        next_open=current.next_open,
    )


@router.get("/quote/{symbol}", response_model=Quote)
async def quote(symbol: str, cache: Cache) -> Quote:
    latest = await cache.get_quote(symbol.upper())
    if latest is None:
        raise HTTPException(
            status_code=404, detail=f"No price for {symbol} yet. Is the market worker running?"
        )
    return latest


@router.get("/candles/{symbol}", response_model=list[Candle])
async def candles(symbol: str, cache: Cache) -> list[Candle]:
    """1-minute candles for the latest session (refreshed by the worker every minute)."""
    return await cache.get_candles(symbol.upper())
