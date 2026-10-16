from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import AuthError, get_or_create_user, verify_token
from app.models import User
from app.services.notifier import Notifier
from app.services.price_cache import PriceCache

_bearer = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_cache(request: Request) -> PriceCache:
    return request.app.state.cache


def get_notifier(request: Request) -> Notifier:
    return request.app.state.notifier


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    try:
        identity = await verify_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return await get_or_create_user(db, identity)


DbSession = Annotated[AsyncSession, Depends(get_db)]
Cache = Annotated[PriceCache, Depends(get_cache)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]
