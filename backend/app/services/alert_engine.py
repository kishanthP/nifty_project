"""The alert engine: compares live prices with active alerts and sends notifications.

How it stays correct:
* One atomic SQL UPDATE flips matching alerts from 'active' to 'triggered'. Postgres
  locks each row while doing it, so even with several workers an alert fires once.
* The notification row is written in that same transaction (an "outbox"). If the
  worker crashes before sending, the retry loop finds the pending row and sends it.
* Between checks (once a second) we remember the highest and lowest price seen, so a
  quick spike that touches your price and comes back is never missed.
* "High & low" alerts with one-cancels-other stop their other side in the same
  transaction that triggers the first side.
* Each user keeps only their latest HISTORY_LIMIT notifications and their latest 10
  triggered / stopped alerts; older ones are deleted when a new alert fires
  (pending notifications are never deleted before sending).
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Numeric, Row, and_, case, delete, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Alert,
    AlertCondition,
    AlertStatus,
    DeviceToken,
    Notification,
    NotificationStatus,
)
from app.schemas.market import Quote
from app.services.alerts import trim_history
from app.services.formatting import format_inr, to_price
from app.services.notifier.base import Notifier, PushMessage
from app.services.price_cache import PriceCache

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 10  # notifications kept per user


@dataclass
class _PriceWindow:
    high: Decimal | None = None
    low: Decimal | None = None
    last_check: float = float("-inf")  # the first tick is always checked


@dataclass(frozen=True)
class TriggeredAlert:
    alert_id: uuid.UUID
    user_id: uuid.UUID
    notification_id: uuid.UUID
    condition: str
    target_price: Decimal
    triggered_price: Decimal
    title: str
    body: str


def build_message(
    name: str,
    condition: str,
    target: Decimal,
    price: Decimal,
    change_pct: float | None,
    note: str | None,
    stopped: list[tuple[str, Decimal]] | None = None,
) -> tuple[str, str]:
    above = condition == AlertCondition.ABOVE
    title = f"{name} {'rose above' if above else 'fell below'} {format_inr(target)}"
    body = f"Now at {format_inr(price)}"
    if change_pct is not None:
        body += f" ({change_pct:+.2f}% today)"
    body += f". Your alert: {condition} {format_inr(target)}."
    for other_condition, other_target in stopped or []:
        body += f" Your other alert ({other_condition} {format_inr(other_target)}) was stopped."
    if note:
        body += f" Note: {note}"
    return title, body[:500]


class AlertEngine:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        notifier: Notifier,
        cache: PriceCache | None = None,
        *,
        check_interval: float = 1.0,
        max_attempts: int = 3,
        expiry_minutes: int = 15,
        frontend_url: str = "",
    ) -> None:
        self.session_factory = session_factory
        self.notifier = notifier
        self.cache = cache
        self.check_interval = check_interval
        self.max_attempts = max_attempts
        self.expiry_minutes = expiry_minutes
        self.frontend_url = frontend_url
        self._windows: dict[int, _PriceWindow] = {}
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------ ticks
    async def on_quote(self, instrument_id: int, quote: Quote) -> list[TriggeredAlert]:
        """Called for every tick. Checks alerts at most once per `check_interval`."""
        window = self._windows.setdefault(instrument_id, _PriceWindow())
        price = to_price(quote.ltp)
        window.high = price if window.high is None else max(window.high, price)
        window.low = price if window.low is None else min(window.low, price)

        now = time.monotonic()
        if now - window.last_check < self.check_interval:
            return []
        high, low = window.high, window.low
        window.high = window.low = None
        window.last_check = now

        triggered = await self.evaluate(instrument_id, quote, high, low)
        if triggered:
            self._spawn(self.dispatch([t.notification_id for t in triggered]))
        return triggered

    async def evaluate(
        self, instrument_id: int, quote: Quote, high: Decimal, low: Decimal
    ) -> list[TriggeredAlert]:
        crossed_price = case(
            (Alert.condition == AlertCondition.ABOVE, literal(high, Numeric(12, 2))),
            else_=literal(low, Numeric(12, 2)),
        )
        stmt = (
            update(Alert)
            .where(
                Alert.instrument_id == instrument_id,
                Alert.status == AlertStatus.ACTIVE,
                or_(
                    and_(Alert.condition == AlertCondition.ABOVE, Alert.target_price <= high),
                    and_(Alert.condition == AlertCondition.BELOW, Alert.target_price >= low),
                ),
            )
            .values(
                status=AlertStatus.TRIGGERED,
                triggered_at=func.now(),
                triggered_price=crossed_price,
            )
            .returning(
                Alert.id,
                Alert.user_id,
                Alert.condition,
                Alert.target_price,
                Alert.triggered_price,
                Alert.note,
                Alert.group_id,
                Alert.one_cancels_other,
            )
            .execution_options(synchronize_session=False)
        )
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).all()
            if not rows:
                return []
            stopped = await self._cancel_other_sides(session, rows)
            triggered: list[TriggeredAlert] = []
            for row in rows:
                title, body = build_message(
                    quote.name,
                    row.condition,
                    row.target_price,
                    row.triggered_price,
                    quote.change_pct,
                    row.note,
                    stopped.get(row.group_id) if row.group_id else None,
                )
                notification = Notification(
                    id=uuid.uuid4(),
                    user_id=row.user_id,
                    alert_id=row.id,
                    channel=self.notifier.channel,
                    title=title,
                    body=body,
                    status=NotificationStatus.PENDING,
                    attempts=0,
                )
                session.add(notification)
                triggered.append(
                    TriggeredAlert(
                        alert_id=row.id,
                        user_id=row.user_id,
                        notification_id=notification.id,
                        condition=row.condition,
                        target_price=row.target_price,
                        triggered_price=row.triggered_price,
                        title=title,
                        body=body,
                    )
                )
            user_ids = {row.user_id for row in rows}
            await self._trim_history(session, user_ids)
            await trim_history(session, user_ids)
            await session.commit()

        for item in triggered:
            logger.info("Alert %s triggered: %s", item.alert_id, item.title)
            if self.cache is not None:
                await self.cache.publish_alert_event(
                    {
                        "type": "alert_triggered",
                        "user_id": str(item.user_id),
                        "alert_id": str(item.alert_id),
                        "notification_id": str(item.notification_id),
                        "symbol": quote.symbol,
                        "condition": item.condition,
                        "target_price": float(item.target_price),
                        "triggered_price": float(item.triggered_price),
                        "title": item.title,
                        "body": item.body,
                    }
                )
        return triggered

    @staticmethod
    async def _cancel_other_sides(
        session: AsyncSession, triggered_rows: Sequence[Row]
    ) -> dict[uuid.UUID, list[tuple[str, Decimal]]]:
        """One-cancels-other: stop the still-active alerts in the groups that just fired.

        Runs in the same transaction as the trigger, so both happen or neither does.
        Returns {group_id: [(condition, target), ...]} of the alerts that were stopped.
        """
        groups = {row.group_id for row in triggered_rows if row.group_id and row.one_cancels_other}
        if not groups:
            return {}
        result = await session.execute(
            update(Alert)
            .where(Alert.group_id.in_(groups), Alert.status == AlertStatus.ACTIVE)
            .values(status=AlertStatus.CANCELLED)
            .returning(Alert.group_id, Alert.condition, Alert.target_price)
            .execution_options(synchronize_session=False)
        )
        stopped: dict[uuid.UUID, list[tuple[str, Decimal]]] = defaultdict(list)
        for group_id, condition, target in result:
            stopped[group_id].append((condition, target))
        return stopped

    @staticmethod
    async def _trim_history(session: AsyncSession, user_ids: set[uuid.UUID]) -> None:
        """Delete each user's notifications beyond the latest HISTORY_LIMIT."""
        await session.flush()
        for user_id in user_ids:
            latest = (
                select(Notification.id)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(HISTORY_LIMIT)
            )
            await session.execute(
                delete(Notification).where(
                    Notification.user_id == user_id,
                    Notification.status != NotificationStatus.PENDING,
                    Notification.id.not_in(latest),
                )
            )

    # ------------------------------------------------------------ delivery
    async def dispatch(self, notification_ids: list[uuid.UUID] | None = None) -> int:
        """Send pending notifications; returns how many were attempted.

        With ids: send exactly those. Without: retry older pending ones (retry loop).
        """
        query = (
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING)
            .with_for_update(skip_locked=True)
        )
        if notification_ids is not None:
            query = query.where(Notification.id.in_(notification_ids))
        else:
            settle = datetime.now(UTC) - timedelta(seconds=10)
            query = (
                query.where(
                    Notification.attempts < self.max_attempts, Notification.created_at < settle
                )
                .order_by(Notification.created_at)
                .limit(100)
            )

        async with self.session_factory() as session:
            notifications = list((await session.scalars(query)).all())
            if not notifications:
                return 0
            user_ids = {n.user_id for n in notifications}
            token_rows = await session.execute(
                select(DeviceToken.user_id, DeviceToken.token).where(
                    DeviceToken.user_id.in_(user_ids)
                )
            )
            tokens_by_user: dict[uuid.UUID, list[str]] = defaultdict(list)
            for user_id, token in token_rows:
                tokens_by_user[user_id].append(token)

            dead_tokens: set[str] = set()
            for notification in notifications:
                tokens = [t for t in tokens_by_user[notification.user_id] if t not in dead_tokens]
                message = PushMessage(
                    title=notification.title,
                    body=notification.body,
                    data={
                        "notification_id": str(notification.id),
                        "alert_id": str(notification.alert_id or ""),
                        "url": self.frontend_url,
                    },
                    tag=f"alert-{notification.alert_id}",
                )
                notification.attempts += 1
                try:
                    result = await self.notifier.send(tokens, message)
                except Exception as exc:  # a bug or outage must not stop other deliveries
                    logger.exception("Notifier crashed for notification %s", notification.id)
                    notification.error = f"Unexpected error: {exc}"
                    if notification.attempts >= self.max_attempts:
                        notification.status = NotificationStatus.FAILED
                    continue
                dead_tokens.update(result.invalid_tokens)
                if result.success_count > 0:
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = datetime.now(UTC)
                    notification.error = None
                elif result.retryable and notification.attempts < self.max_attempts:
                    notification.error = result.error
                else:
                    notification.status = NotificationStatus.FAILED
                    notification.error = result.error or "Delivery failed"

            if dead_tokens:
                await session.execute(delete(DeviceToken).where(DeviceToken.token.in_(dead_tokens)))
                logger.info("Removed %d expired device tokens", len(dead_tokens))
            await session.commit()
            return len(notifications)

    async def retry_pending(self) -> None:
        """Give up on very old pending notifications, then retry the rest."""
        cutoff = datetime.now(UTC) - timedelta(minutes=self.expiry_minutes)
        async with self.session_factory() as session:
            await session.execute(
                update(Notification)
                .where(
                    Notification.status == NotificationStatus.PENDING,
                    Notification.created_at < cutoff,
                )
                .values(
                    status=NotificationStatus.FAILED, error="Expired before it could be delivered"
                )
            )
            await session.commit()
        await self.dispatch()

    # ------------------------------------------------------------ housekeeping
    def _spawn(self, coro) -> None:  # noqa: ANN001
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Notification dispatch failed", exc_info=task.exception())

    async def drain(self) -> None:
        """Wait for in-flight deliveries (used on shutdown and in tests)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
