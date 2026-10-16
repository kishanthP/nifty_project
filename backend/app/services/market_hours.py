"""NSE trading hours in Indian Standard Time.

Regular session: 09:15–15:30 IST, Monday to Friday, except exchange holidays.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
# The live feed connects a little before the open and stays a little after the close.
STREAM_START = time(9, 0)
STREAM_END = time(15, 35)

_HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "nse_holidays.json"

ClosedReason = Literal["open", "weekend", "holiday", "pre_open", "after_hours"]


@dataclass(frozen=True)
class MarketStatus:
    is_open: bool
    reason: ClosedReason
    holiday_name: str | None
    next_open: datetime


@lru_cache
def holidays() -> dict[date, str]:
    data = json.loads(_HOLIDAYS_FILE.read_text(encoding="utf-8"))
    return {date.fromisoformat(item["date"]): item["name"] for item in data["holidays"]}


def now_ist() -> datetime:
    return datetime.now(IST)


def _to_ist(moment: datetime | None) -> datetime:
    if moment is None:
        return now_ist()
    if moment.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return moment.astimezone(IST)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays()


def is_market_open(moment: datetime | None = None) -> bool:
    current = _to_ist(moment)
    return is_trading_day(current.date()) and MARKET_OPEN <= current.time() < MARKET_CLOSE


def in_stream_window(moment: datetime | None = None) -> bool:
    current = _to_ist(moment)
    return is_trading_day(current.date()) and STREAM_START <= current.time() < STREAM_END


def next_open(moment: datetime | None = None) -> datetime:
    """The next time the market opens (strictly after `moment` if it is already open)."""
    current = _to_ist(moment)
    day = current.date()
    if current.time() >= MARKET_OPEN:
        day += timedelta(days=1)
    while not is_trading_day(day):
        day += timedelta(days=1)
    return datetime.combine(day, MARKET_OPEN, tzinfo=IST)


def seconds_until_stream_window(moment: datetime | None = None) -> float:
    current = _to_ist(moment)
    if in_stream_window(current):
        return 0.0
    day = current.date()
    if current.time() >= STREAM_START:
        day += timedelta(days=1)
    while not is_trading_day(day):
        day += timedelta(days=1)
    start = datetime.combine(day, STREAM_START, tzinfo=IST)
    return (start - current).total_seconds()


def last_session_date(moment: datetime | None = None) -> date:
    """The most recent trading day whose session has started (today if open or closed today)."""
    current = _to_ist(moment)
    day = current.date()
    if not is_trading_day(day) or current.time() < MARKET_OPEN:
        day -= timedelta(days=1)
        while not is_trading_day(day):
            day -= timedelta(days=1)
    return day


def market_status(moment: datetime | None = None) -> MarketStatus:
    current = _to_ist(moment)
    today = current.date()
    upcoming = next_open(current)
    if current.weekday() >= 5:
        return MarketStatus(False, "weekend", None, upcoming)
    if today in holidays():
        return MarketStatus(False, "holiday", holidays()[today], upcoming)
    if current.time() < MARKET_OPEN:
        return MarketStatus(False, "pre_open", None, upcoming)
    if current.time() >= MARKET_CLOSE:
        return MarketStatus(False, "after_hours", None, upcoming)
    return MarketStatus(True, "open", None, upcoming)
