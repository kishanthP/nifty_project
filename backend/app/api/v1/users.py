from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Notification
from app.schemas.users import NotificationOut, UserOut
from app.services.alert_engine import HISTORY_LIMIT

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/notifications", response_model=list[NotificationOut])
async def notifications(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=HISTORY_LIMIT)] = HISTORY_LIMIT,
) -> list[NotificationOut]:
    rows = await db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return [NotificationOut.model_validate(row) for row in rows]
