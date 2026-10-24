import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Alert, AlertStatus, DeviceToken, Notification, User
from app.services.alert_engine import HISTORY_LIMIT, AlertEngine
from app.services.notifier.base import SendResult
from tests.conftest import FakeNotifier, make_quote


async def _add_alert(
    session_factory: async_sessionmaker,
    user: User,
    instrument_id: int,
    condition: str,
    target: str,
    status: str = AlertStatus.ACTIVE,
) -> Alert:
    async with session_factory() as session:
        alert = Alert(
            user_id=user.id,
            instrument_id=instrument_id,
            condition=condition,
            target_price=Decimal(target),
            status=status,
        )
        session.add(alert)
        await session.commit()
        return alert


async def _add_token(session_factory: async_sessionmaker, user: User, token: str) -> None:
    async with session_factory() as session:
        session.add(DeviceToken(user_id=user.id, token=token))
        await session.commit()


async def _statuses(session_factory: async_sessionmaker) -> dict[str, str]:
    async with session_factory() as session:
        rows = await session.execute(select(Alert.target_price, Alert.condition, Alert.status))
        return {f"{c} {t}": s for t, c, s in rows}


def _engine(
    session_factory: async_sessionmaker, notifier: FakeNotifier, interval: float = 0
) -> AlertEngine:
    return AlertEngine(session_factory, notifier, check_interval=interval)


async def test_above_and_below_fire_only_when_crossed(
    session_factory, user, nifty_id, notifier
) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    await _add_alert(session_factory, user, nifty_id, "below", "22540")
    await _add_alert(
        session_factory, user, nifty_id, "above", "22555", status=AlertStatus.CANCELLED
    )
    engine = _engine(session_factory, notifier)

    assert await engine.on_quote(nifty_id, make_quote(22550)) == []

    fired = await engine.on_quote(nifty_id, make_quote(22560.0))
    assert [(f.condition, f.target_price) for f in fired] == [("above", Decimal("22560.00"))]
    assert fired[0].title == "NIFTY 50 rose above 22,560.00"

    fired = await engine.on_quote(nifty_id, make_quote(22539.95))
    assert [(f.condition, f.triggered_price) for f in fired] == [("below", Decimal("22539.95"))]

    statuses = await _statuses(session_factory)
    assert statuses == {
        "above 22560.00": "triggered",
        "below 22540.00": "triggered",
        "above 22555.00": "cancelled",  # cancelled alerts never fire
    }
    await engine.drain()


async def test_alert_never_fires_twice(session_factory, user, nifty_id, notifier) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    engine = _engine(session_factory, notifier)
    assert len(await engine.on_quote(nifty_id, make_quote(22561))) == 1
    assert await engine.on_quote(nifty_id, make_quote(22570)) == []
    await engine.drain()


async def test_parallel_workers_trigger_once(session_factory, user, nifty_id, notifier) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    quote = make_quote(22565)
    results = await asyncio.gather(
        *(
            _engine(session_factory, notifier).evaluate(
                nifty_id, quote, Decimal("22565"), Decimal("22565")
            )
            for _ in range(5)
        )
    )
    assert sum(len(r) for r in results) == 1
    async with session_factory() as session:
        assert len((await session.scalars(select(Notification))).all()) == 1


async def test_quick_spike_between_checks_is_caught(
    session_factory, user, nifty_id, notifier
) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22600")
    engine = _engine(session_factory, notifier, interval=3600)
    await engine.on_quote(nifty_id, make_quote(22550))  # first tick checks immediately
    await engine.on_quote(nifty_id, make_quote(22605))  # spike, inside the throttle window
    engine._windows[nifty_id].last_check = float("-inf")  # time for the next check
    fired = await engine.on_quote(nifty_id, make_quote(22551))  # price already back down
    assert len(fired) == 1 and fired[0].triggered_price == Decimal("22605.00")
    await engine.drain()


async def test_delivery_marks_sent_and_drops_dead_tokens(
    session_factory, user, nifty_id, notifier
) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    await _add_token(session_factory, user, "good-token-" + "x" * 20)
    await _add_token(session_factory, user, "dead-token-" + "x" * 20)
    notifier.responder = lambda tokens: SendResult(
        success_count=1, failure_count=1, invalid_tokens=[t for t in tokens if t.startswith("dead")]
    )
    engine = _engine(session_factory, notifier)
    await engine.on_quote(nifty_id, make_quote(22560))
    await engine.drain()

    sent_tokens, message = notifier.sent[0]
    assert sorted(sent_tokens) == sorted(["good-token-" + "x" * 20, "dead-token-" + "x" * 20])
    assert "Now at 22,560.00" in message.body
    async with session_factory() as session:
        notification = await session.scalar(select(Notification))
        assert notification is not None and notification.status == "sent"
        tokens = (await session.scalars(select(DeviceToken.token))).all()
        assert tokens == ["good-token-" + "x" * 20]


async def test_no_devices_marks_failed(session_factory, user, nifty_id, notifier) -> None:
    await _add_alert(session_factory, user, nifty_id, "below", "22540")
    engine = _engine(session_factory, notifier)
    await engine.on_quote(nifty_id, make_quote(22500))
    await engine.drain()
    async with session_factory() as session:
        notification = await session.scalar(select(Notification))
        assert notification is not None and notification.status == "failed"
        assert "No devices" in (notification.error or "")


async def test_temporary_failure_is_retried_then_sent(
    session_factory, user, nifty_id, notifier
) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    await _add_token(session_factory, user, "token-" + "x" * 30)
    notifier.responder = lambda tokens: SendResult(
        failure_count=1, error="FCM unavailable", retryable=True
    )
    engine = _engine(session_factory, notifier)
    await engine.on_quote(nifty_id, make_quote(22561))
    await engine.drain()

    async with session_factory() as session:
        notification = await session.scalar(select(Notification))
        assert notification is not None
        assert (notification.status, notification.attempts) == ("pending", 1)
        # Pretend the retry loop runs a minute later and FCM is back.
        await session.execute(
            update(Notification).values(created_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()

    notifier.responder = None
    await engine.retry_pending()
    async with session_factory() as session:
        notification = await session.scalar(select(Notification))
        assert notification is not None and notification.status == "sent"


async def test_crash_before_send_is_recovered(session_factory, user, nifty_id, notifier) -> None:
    """The notification row is saved with the trigger, so a crash can't lose it."""
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    await _add_token(session_factory, user, "token-" + "x" * 30)
    engine = _engine(session_factory, notifier)
    # evaluate() = trigger + outbox row, but no delivery (as if the worker died here).
    await engine.evaluate(nifty_id, make_quote(22561), Decimal("22561"), Decimal("22561"))
    assert notifier.sent == []

    async with session_factory() as session:
        await session.execute(
            update(Notification).values(created_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    await engine.retry_pending()
    assert len(notifier.sent) == 1


async def test_very_old_pending_notifications_expire(
    session_factory, user, nifty_id, notifier
) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    engine = _engine(session_factory, notifier)
    await engine.evaluate(nifty_id, make_quote(22561), Decimal("22561"), Decimal("22561"))
    async with session_factory() as session:
        await session.execute(
            update(Notification).values(created_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()
    await engine.retry_pending()
    assert notifier.sent == []
    async with session_factory() as session:
        notification = await session.scalar(select(Notification))
        assert notification is not None and notification.status == "failed"


# ---------------------------------------------------------------- high & low (range) alerts
async def _add_pair(
    session_factory: async_sessionmaker, user: User, instrument_id: int, oco: bool
) -> uuid.UUID:
    group_id = uuid.uuid4()
    async with session_factory() as session:
        for condition, target in (("above", "22560"), ("below", "22540")):
            session.add(
                Alert(
                    user_id=user.id,
                    instrument_id=instrument_id,
                    condition=condition,
                    target_price=Decimal(target),
                    status=AlertStatus.ACTIVE,
                    group_id=group_id,
                    one_cancels_other=oco,
                )
            )
        await session.commit()
    return group_id


async def test_range_without_oco_keeps_other_side(
    session_factory, user, nifty_id, notifier
) -> None:
    await _add_pair(session_factory, user, nifty_id, oco=False)
    engine = _engine(session_factory, notifier)
    assert len(await engine.on_quote(nifty_id, make_quote(22561))) == 1
    assert await _statuses(session_factory) == {
        "above 22560.00": "triggered",
        "below 22540.00": "active",  # still watching the low side
    }
    # Later the price falls through the low: that side fires too.
    fired = await engine.on_quote(nifty_id, make_quote(22539))
    assert [f.condition for f in fired] == ["below"]
    await engine.drain()


async def test_range_with_oco_stops_other_side(session_factory, user, nifty_id, notifier) -> None:
    await _add_pair(session_factory, user, nifty_id, oco=True)
    engine = _engine(session_factory, notifier)
    fired = await engine.on_quote(nifty_id, make_quote(22561))
    assert len(fired) == 1
    assert "Your other alert (below 22,540.00) was stopped." in fired[0].body
    assert await _statuses(session_factory) == {
        "above 22560.00": "triggered",
        "below 22540.00": "cancelled",
    }
    # The stopped side never fires, even when its price is reached.
    assert await engine.on_quote(nifty_id, make_quote(22530)) == []
    await engine.drain()
    async with session_factory() as session:
        assert len((await session.scalars(select(Notification))).all()) == 1


async def test_history_keeps_only_latest_ten(session_factory, user, nifty_id, notifier) -> None:
    old = datetime.now(UTC) - timedelta(days=1)
    async with session_factory() as session:
        for i in range(HISTORY_LIMIT + 3):
            session.add(
                Notification(
                    user_id=user.id,
                    channel="log",
                    title=f"old {i}",
                    body="",
                    status="sent",
                    created_at=old + timedelta(minutes=i),
                )
            )
        await session.commit()

    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    await _engine(session_factory, notifier).on_quote(nifty_id, make_quote(22561))

    async with session_factory() as session:
        titles = list(
            await session.scalars(
                select(Notification.title).order_by(Notification.created_at.desc())
            )
        )
    assert len(titles) == HISTORY_LIMIT
    assert not titles[0].startswith("old")  # the new one is kept
    assert "old 0" not in titles and "old 12" in titles  # the oldest went first


async def test_multiple_levels_fire_one_by_one(session_factory, user, nifty_id, notifier) -> None:
    await _add_alert(session_factory, user, nifty_id, "above", "22310")
    await _add_alert(session_factory, user, nifty_id, "above", "22320")
    engine = _engine(session_factory, notifier)
    first = await engine.on_quote(nifty_id, make_quote(22315))
    assert [a.target_price for a in first] == [Decimal("22310")]
    second = await engine.on_quote(nifty_id, make_quote(22321))
    assert [a.target_price for a in second] == [Decimal("22320")]


async def test_alert_history_keeps_only_latest_ten(
    session_factory, user, nifty_id, notifier
) -> None:
    old = datetime.now(UTC) - timedelta(days=1)
    async with session_factory() as session:
        for i in range(12):
            session.add(
                Alert(
                    user_id=user.id,
                    instrument_id=nifty_id,
                    condition="above",
                    target_price=Decimal(22000 + i),
                    status=AlertStatus.TRIGGERED,
                    triggered_at=old + timedelta(minutes=i),
                    triggered_price=Decimal(22000 + i),
                )
            )
        await session.commit()
    await _add_alert(session_factory, user, nifty_id, "above", "22560")
    await _add_alert(session_factory, user, nifty_id, "above", "22700")  # stays active
    await _engine(session_factory, notifier).on_quote(nifty_id, make_quote(22561))

    statuses = await _statuses(session_factory)
    history = [key for key, status in statuses.items() if status != AlertStatus.ACTIVE]
    assert len(history) == 10
    assert "above 22560.00" in history  # the newest is kept
    assert "above 22000.00" not in history and "above 22001.00" not in history  # oldest deleted
    assert statuses["above 22700.00"] == AlertStatus.ACTIVE
