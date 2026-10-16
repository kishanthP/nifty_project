"""Login: the React app signs in with Google via Firebase and sends us the Firebase
ID token. We verify it with firebase-admin and find (or create) the matching user.

AUTH_DEV_MODE=true also accepts tokens like "dev:you@example.com" so the app can be
tried before Firebase is set up. It is refused in production (see config.py).
"""

import asyncio
import logging
import re
from dataclasses import dataclass

from firebase_admin import auth as firebase_auth
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.firebase import get_firebase_app
from app.models import User

logger = logging.getLogger(__name__)

_DEV_PREFIX = "dev:"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class Identity:
    uid: str
    email: str | None
    name: str | None
    picture: str | None


async def verify_token(token: str) -> Identity:
    settings = get_settings()
    if token.startswith(_DEV_PREFIX):
        if not settings.auth_dev_mode:
            raise AuthError("Dev login is disabled")
        email = token[len(_DEV_PREFIX) :].strip().lower()
        if not _EMAIL_RE.match(email):
            raise AuthError("Dev login needs a valid email")
        return Identity(uid=f"dev:{email}", email=email, name=email.split("@")[0], picture=None)

    app = get_firebase_app()
    if app is None:
        raise AuthError("Google login is not configured on the server yet", status_code=503)
    try:
        claims = await asyncio.to_thread(
            firebase_auth.verify_id_token, token, app=app, clock_skew_seconds=10
        )
    except (
        ValueError,
        firebase_auth.InvalidIdTokenError,
        firebase_auth.ExpiredIdTokenError,
    ) as exc:
        raise AuthError("Your session has expired. Please sign in again.") from exc
    except firebase_auth.CertificateFetchError as exc:
        logger.warning("Could not fetch Firebase certificates: %s", exc)
        raise AuthError("Login service temporarily unavailable", status_code=503) from exc
    return Identity(
        uid=claims["uid"],
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


async def get_or_create_user(db: AsyncSession, identity: Identity) -> User:
    user = await db.scalar(select(User).where(User.firebase_uid == identity.uid))
    if user is None:
        # ON CONFLICT handles two first requests arriving at the same time.
        result = await db.execute(
            pg_insert(User)
            .values(
                firebase_uid=identity.uid,
                email=identity.email,
                display_name=identity.name,
                photo_url=identity.picture,
            )
            .on_conflict_do_nothing(index_elements=[User.firebase_uid])
        )
        await db.commit()
        if result.rowcount:  # 0 when a parallel request created the user first
            logger.info("New user %s", identity.email or identity.uid)
        user = await db.scalar(select(User).where(User.firebase_uid == identity.uid))
        assert user is not None
        return user

    changed = False
    for field, value in (
        ("email", identity.email),
        ("display_name", identity.name),
        ("photo_url", identity.picture),
    ):
        if value and getattr(user, field) != value:
            setattr(user, field, value)
            changed = True
    if changed:
        await db.commit()
    return user
