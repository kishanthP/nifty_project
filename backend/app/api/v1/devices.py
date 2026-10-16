from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import AppSettings, CurrentUser, DbSession, NotifierDep
from app.models import DeviceToken
from app.schemas.users import DeviceRegister, DeviceUnregister, TestPushResult
from app.services.notifier import PushMessage

router = APIRouter()


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(
    data: DeviceRegister, user: CurrentUser, db: DbSession, settings: AppSettings
) -> Response:
    """Save this browser's FCM token so alerts can be pushed to it."""
    now = datetime.now(UTC)
    await db.execute(
        pg_insert(DeviceToken)
        .values(user_id=user.id, token=data.token, user_agent=data.user_agent, last_seen_at=now)
        .on_conflict_do_update(
            index_elements=[DeviceToken.token],
            # The same browser may switch accounts: the token moves to the new user.
            set_={"user_id": user.id, "user_agent": data.user_agent, "last_seen_at": now},
        )
    )
    # Keep only the most recent devices per user.
    stale_ids = (
        select(DeviceToken.id)
        .where(DeviceToken.user_id == user.id)
        .order_by(DeviceToken.last_seen_at.desc())
        .offset(settings.max_devices_per_user)
    )
    await db.execute(delete(DeviceToken).where(DeviceToken.id.in_(stale_ids)))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/unregister", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(data: DeviceUnregister, user: CurrentUser, db: DbSession) -> Response:
    await db.execute(
        delete(DeviceToken).where(DeviceToken.token == data.token, DeviceToken.user_id == user.id)
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/test", response_model=TestPushResult)
async def send_test_push(user: CurrentUser, db: DbSession, notifier: NotifierDep) -> TestPushResult:
    """Send a test notification to all of your devices."""
    tokens = list(await db.scalars(select(DeviceToken.token).where(DeviceToken.user_id == user.id)))
    result = await notifier.send(
        tokens,
        PushMessage(
            title="Test notification",
            body="Push notifications are working. You'll get price alerts like this one.",
            tag="test",
        ),
    )
    if result.invalid_tokens:
        await db.execute(delete(DeviceToken).where(DeviceToken.token.in_(result.invalid_tokens)))
        await db.commit()
    return TestPushResult(
        channel=notifier.channel,
        devices=len(tokens),
        delivered=result.success_count,
        error=result.error,
    )
