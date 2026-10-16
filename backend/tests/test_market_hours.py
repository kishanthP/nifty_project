from datetime import date, datetime

from app.services import market_hours as mh


def ist(*args: int) -> datetime:
    return datetime(*args, tzinfo=mh.IST)


def test_open_during_session() -> None:
    status = mh.market_status(ist(2026, 10, 15, 10, 0))  # Thursday
    assert status.is_open and status.reason == "open"


def test_pre_open_and_stream_window() -> None:
    moment = ist(2026, 10, 15, 9, 5)
    assert not mh.is_market_open(moment)
    assert mh.in_stream_window(moment)
    assert mh.market_status(moment).reason == "pre_open"


def test_closes_at_1530() -> None:
    assert mh.is_market_open(ist(2026, 10, 15, 15, 29))
    assert not mh.is_market_open(ist(2026, 10, 15, 15, 30))
    assert mh.market_status(ist(2026, 10, 15, 16, 0)).reason == "after_hours"


def test_weekend_next_open_is_monday() -> None:
    status = mh.market_status(ist(2026, 10, 17, 11, 0))  # Saturday
    assert status.reason == "weekend"
    assert status.next_open == ist(2026, 10, 19, 9, 15)


def test_holiday_is_closed() -> None:
    status = mh.market_status(ist(2026, 10, 20, 11, 0))  # Dussehra (Tuesday)
    assert status.reason == "holiday"
    assert status.holiday_name == "Dussehra"
    assert status.next_open == ist(2026, 10, 21, 9, 15)


def test_last_session_date_skips_weekend() -> None:
    assert mh.last_session_date(ist(2026, 10, 19, 8, 0)) == date(2026, 10, 16)  # Mon pre-open → Fri
    assert mh.last_session_date(ist(2026, 10, 19, 12, 0)) == date(2026, 10, 19)


def test_seconds_until_stream_window_over_weekend() -> None:
    # Friday 16:00 → Monday 09:00 is 65 hours.
    assert mh.seconds_until_stream_window(ist(2026, 10, 16, 16, 0)) == 65 * 3600
