"""Business rules for creating, changing and listing alerts (used by the API)."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertCondition, AlertStatus, Instrument, User
from app.schemas.alerts import (
    AlertBatchCreate,
    AlertCreate,
    AlertOut,
    AlertRangeCreate,
    AlertUpdate,
)
from app.schemas.market import Quote
from app.services.formatting import format_inr, to_price


class AlertError(Exception):
    """A problem the user can fix; the message is shown in the app."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def infer_condition(target: Decimal, current: Decimal) -> AlertCondition:
    if target > current:
        return AlertCondition.ABOVE
    if target < current:
        return AlertCondition.BELOW
    raise AlertError(f"{format_inr(target)} is the current price. Pick a price above or below it.")


def is_condition_met(condition: str, target: Decimal, current: Decimal) -> bool:
    if condition == AlertCondition.ABOVE:
        return current >= target
    return current <= target


def ensure_not_met(name: str, condition: str, target: Decimal, current: Decimal) -> None:
    if not is_condition_met(condition, target, current):
        return
    if condition == AlertCondition.ABOVE:
        raise AlertError(
            f"{name} is already at or above {format_inr(target)} (now {format_inr(current)}). "
            "Choose a higher price, or switch to 'below'."
        )
    raise AlertError(
        f"{name} is already at or below {format_inr(target)} (now {format_inr(current)}). "
        "Choose a lower price, or switch to 'above'."
    )


def to_out(alert: Alert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        symbol=alert.instrument.symbol,
        instrument_name=alert.instrument.name,
        condition=AlertCondition(alert.condition),
        target_price=alert.target_price,
        base_price=alert.base_price,
        status=alert.status,
        note=alert.note,
        triggered_at=alert.triggered_at,
        triggered_price=alert.triggered_price,
        group_id=alert.group_id,
        one_cancels_other=alert.one_cancels_other,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


async def get_active_instrument(db: AsyncSession, symbol: str) -> Instrument:
    instrument = await db.scalar(
        select(Instrument).where(Instrument.symbol == symbol.upper(), Instrument.is_active)
    )
    if instrument is None:
        raise AlertError(f"Unknown symbol {symbol}", status_code=404)
    return instrument


async def _count_active(db: AsyncSession, user: User) -> int:
    return (
        await db.scalar(
            select(func.count()).where(Alert.user_id == user.id, Alert.status == AlertStatus.ACTIVE)
        )
        or 0
    )


async def create_alert(
    db: AsyncSession, user: User, data: AlertCreate, quote: Quote | None, max_active: int
) -> Alert:
    instrument = await get_active_instrument(db, data.symbol)
    if await _count_active(db, user) >= max_active:
        raise AlertError(f"You can have at most {max_active} active alerts. Delete some first.")

    target = to_price(data.target_price)
    current = to_price(quote.ltp) if quote else None
    condition = data.condition
    if condition is None:
        if current is None:
            raise AlertError("Live price is not available yet. Choose 'above' or 'below'.")
        condition = infer_condition(target, current)
    if current is not None:
        ensure_not_met(instrument.name, condition, target, current)

    alert = Alert(
        user_id=user.id,
        instrument_id=instrument.id,
        condition=condition,
        target_price=target,
        base_price=current,
        status=AlertStatus.ACTIVE,
        note=(data.note or "").strip() or None,
    )
    alert.instrument = instrument
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


async def create_range_alert(
    db: AsyncSession, user: User, data: AlertRangeCreate, quote: Quote | None, max_active: int
) -> list[Alert]:
    """'High & low': two linked alerts (above high, below low) saved in one transaction."""
    instrument = await get_active_instrument(db, data.symbol)
    if await _count_active(db, user) + 2 > max_active:
        raise AlertError(f"You can have at most {max_active} active alerts. Delete some first.")

    high = to_price(data.high_price)
    low = to_price(data.low_price)
    if high <= low:
        raise AlertError("The high price must be above the low price.")
    current = to_price(quote.ltp) if quote else None
    if current is not None:
        if current >= high:
            raise AlertError(
                f"{instrument.name} is already at or above {format_inr(high)} "
                f"(now {format_inr(current)}). Choose a higher high price."
            )
        if current <= low:
            raise AlertError(
                f"{instrument.name} is already at or below {format_inr(low)} "
                f"(now {format_inr(current)}). Choose a lower low price."
            )

    group_id = uuid.uuid4()
    note = (data.note or "").strip() or None
    alerts = []
    for condition, target in ((AlertCondition.ABOVE, high), (AlertCondition.BELOW, low)):
        alert = Alert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=condition,
            target_price=target,
            base_price=current,
            status=AlertStatus.ACTIVE,
            note=note,
            group_id=group_id,
            one_cancels_other=data.one_cancels_other,
        )
        alert.instrument = instrument
        alerts.append(alert)
    db.add_all(alerts)
    await db.commit()
    for alert in alerts:
        await db.refresh(alert)
    return alerts


async def create_batch_alerts(
    db: AsyncSession, user: User, data: AlertBatchCreate, quote: Quote | None, max_active: int
) -> list[Alert]:
    """'Multiple': independent alerts saved in one transaction (all or nothing)."""
    instrument = await get_active_instrument(db, data.symbol)
    if await _count_active(db, user) + len(data.items) > max_active:
        raise AlertError(f"You can have at most {max_active} active alerts. Delete some first.")

    current = to_price(quote.ltp) if quote else None
    note = (data.note or "").strip() or None
    seen: set[tuple[AlertCondition, Decimal]] = set()
    alerts = []
    for item in data.items:
        target = to_price(item.target_price)
        condition = item.condition
        if condition is None:
            if current is None:
                raise AlertError("Live price is not available yet. Choose 'above' or 'below'.")
            condition = infer_condition(target, current)
        if (condition, target) in seen:
            raise AlertError(f"{format_inr(target)} ({condition}) is listed twice.")
        seen.add((condition, target))
        if current is not None:
            ensure_not_met(instrument.name, condition, target, current)
        alert = Alert(
            user_id=user.id,
            instrument_id=instrument.id,
            condition=condition,
            target_price=target,
            base_price=current,
            status=AlertStatus.ACTIVE,
            note=note,
        )
        alert.instrument = instrument
        alerts.append(alert)
    db.add_all(alerts)
    await db.commit()
    for alert in alerts:
        await db.refresh(alert)
    return alerts


async def get_user_alert(db: AsyncSession, user: User, alert_id: uuid.UUID) -> Alert:
    alert = await db.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    if alert is None:
        raise AlertError("Alert not found", status_code=404)
    return alert


async def update_alert(
    db: AsyncSession,
    user: User,
    alert_id: uuid.UUID,
    data: AlertUpdate,
    quote: Quote | None,
    max_active: int,
) -> Alert:
    alert = await get_user_alert(db, user, alert_id)
    target = to_price(data.target_price) if data.target_price is not None else alert.target_price
    condition = data.condition or AlertCondition(alert.condition)
    new_status = data.status or alert.status
    current = to_price(quote.ltp) if quote else None

    if new_status == AlertStatus.ACTIVE:
        reactivating = alert.status != AlertStatus.ACTIVE
        if reactivating and await _count_active(db, user) >= max_active:
            raise AlertError(f"You can have at most {max_active} active alerts.")
        if current is not None:
            ensure_not_met(alert.instrument.name, condition, target, current)
        if reactivating:
            alert.triggered_at = None
            alert.triggered_price = None
            alert.base_price = current

    alert.target_price = target
    alert.condition = condition
    alert.status = new_status
    if data.note is not None:
        alert.note = data.note.strip() or None
    await db.commit()
    await db.refresh(alert)
    return alert


async def delete_alert(db: AsyncSession, user: User, alert_id: uuid.UUID) -> None:
    alert = await get_user_alert(db, user, alert_id)
    await db.delete(alert)
    await db.commit()


async def list_alerts(db: AsyncSession, user: User, statuses: list[str] | None) -> list[Alert]:
    query = select(Alert).where(Alert.user_id == user.id)
    if statuses:
        query = query.where(Alert.status.in_(statuses))
    query = query.order_by(Alert.status, Alert.updated_at.desc()).limit(200)
    return list((await db.scalars(query)).all())
