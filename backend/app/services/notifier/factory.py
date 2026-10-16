from app.core.firebase import get_firebase_app
from app.services.notifier.base import Notifier
from app.services.notifier.fcm import FcmNotifier
from app.services.notifier.log import LogNotifier


def build_notifier() -> Notifier:
    app = get_firebase_app()
    return FcmNotifier(app) if app is not None else LogNotifier()
