"""Shared Firebase Admin app, used for verifying logins and sending push notifications."""

import logging
from functools import lru_cache
from pathlib import Path

import firebase_admin
from firebase_admin import credentials

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_APP_NAME = "share-market"


@lru_cache
def get_firebase_app() -> firebase_admin.App | None:
    """Return the Firebase app, or None when the service-account file is missing."""
    path = get_settings().firebase_credentials_file
    if not path or not Path(path).is_file():
        logger.warning(
            "Firebase credentials not found (FIREBASE_CREDENTIALS_FILE=%s). "
            "Google login and push notifications are disabled.",
            path,
        )
        return None
    return firebase_admin.initialize_app(credentials.Certificate(path), name=_APP_NAME)
