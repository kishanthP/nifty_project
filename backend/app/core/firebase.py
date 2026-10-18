"""Shared Firebase Admin app, used for verifying logins and sending push notifications."""

import base64
import json
import logging
from functools import lru_cache
from pathlib import Path

import firebase_admin
from firebase_admin import credentials

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_APP_NAME = "share-market"


def _credentials_from_json(raw: str) -> credentials.Certificate | None:
    """FIREBASE_CREDENTIALS_JSON: the service-account JSON, as text or base64."""
    try:
        text = raw if raw.startswith("{") else base64.b64decode(raw).decode()
        return credentials.Certificate(json.loads(text))
    except ValueError as exc:  # bad JSON, bad base64 or not a service account
        # Never log the value itself: it contains the private key.
        logger.error("FIREBASE_CREDENTIALS_JSON is not a valid service-account key (%s)", exc)
        return None


@lru_cache
def get_firebase_app() -> firebase_admin.App | None:
    """Return the Firebase app, or None when no service-account key is configured."""
    settings = get_settings()
    raw = settings.firebase_credentials_json.get_secret_value().strip()
    if raw:
        cert = _credentials_from_json(raw)
        return firebase_admin.initialize_app(cert, name=_APP_NAME) if cert else None

    path = settings.firebase_credentials_file
    if not path or not Path(path).is_file():
        logger.warning(
            "Firebase credentials not found (FIREBASE_CREDENTIALS_FILE=%s). "
            "Google login and push notifications are disabled.",
            path,
        )
        return None
    return firebase_admin.initialize_app(credentials.Certificate(path), name=_APP_NAME)
