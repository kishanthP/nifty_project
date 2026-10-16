import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import AppSettings, Cache, CurrentUser, DbSession
from app.schemas.alerts import AlertCreate, AlertOut, AlertRangeCreate, AlertUpdate
from app.services import alerts as alert_service
from app.services.alerts import AlertError

router = APIRouter()

StatusFilter = Literal["active", "triggered", "cancelled"]


def _http_error(exc: AlertError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[list[StatusFilter] | None, Query(alias="status")] = None,
) -> list[AlertOut]:
    rows = await alert_service.list_alerts(db, user, list(status_filter or []))
    return [alert_service.to_out(row) for row in rows]


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    data: AlertCreate, user: CurrentUser, db: DbSession, cache: Cache, settings: AppSettings
) -> AlertOut:
    quote = await cache.get_quote(data.symbol.upper())
    try:
        alert = await alert_service.create_alert(
            db, user, data, quote, settings.max_active_alerts_per_user
        )
    except AlertError as exc:
        raise _http_error(exc) from exc
    return alert_service.to_out(alert)


@router.post("/range", response_model=list[AlertOut], status_code=status.HTTP_201_CREATED)
async def create_range_alert(
    data: AlertRangeCreate, user: CurrentUser, db: DbSession, cache: Cache, settings: AppSettings
) -> list[AlertOut]:
    """High & low: one alert above `high_price` and one below `low_price`, created together."""
    quote = await cache.get_quote(data.symbol.upper())
    try:
        alerts = await alert_service.create_range_alert(
            db, user, data, quote, settings.max_active_alerts_per_user
        )
    except AlertError as exc:
        raise _http_error(exc) from exc
    return [alert_service.to_out(alert) for alert in alerts]


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: uuid.UUID,
    data: AlertUpdate,
    user: CurrentUser,
    db: DbSession,
    cache: Cache,
    settings: AppSettings,
) -> AlertOut:
    try:
        existing = await alert_service.get_user_alert(db, user, alert_id)
        quote = await cache.get_quote(existing.instrument.symbol)
        alert = await alert_service.update_alert(
            db, user, alert_id, data, quote, settings.max_active_alerts_per_user
        )
    except AlertError as exc:
        raise _http_error(exc) from exc
    return alert_service.to_out(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    try:
        await alert_service.delete_alert(db, user, alert_id)
    except AlertError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
