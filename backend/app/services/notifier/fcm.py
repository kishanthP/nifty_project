"""Firebase Cloud Messaging: free push notifications to browsers (and later, phones)."""

import asyncio
import logging

import firebase_admin
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging

from app.services.notifier.base import PushMessage, SendResult

logger = logging.getLogger(__name__)

_MAX_TOKENS_PER_CALL = 500  # FCM multicast limit


class FcmNotifier:
    channel = "fcm"

    def __init__(self, app: firebase_admin.App) -> None:
        self.app = app

    def _build(self, tokens: list[str], message: PushMessage) -> messaging.MulticastMessage:
        data = {"title": message.title, "body": message.body, **message.data}
        return messaging.MulticastMessage(
            tokens=tokens,
            data=data,
            notification=messaging.Notification(title=message.title, body=message.body),
            webpush=messaging.WebpushConfig(
                headers={"Urgency": "high", "TTL": "600"},
                notification=messaging.WebpushNotification(
                    title=message.title,
                    body=message.body,
                    icon="/icon-192.png",
                    tag=message.tag,
                    require_interaction=True,
                ),
            ),
        )

    async def send(self, tokens: list[str], message: PushMessage) -> SendResult:
        result = SendResult()
        if not tokens:
            result.error = "No devices registered for push notifications"
            return result
        for start in range(0, len(tokens), _MAX_TOKENS_PER_CALL):
            batch = tokens[start : start + _MAX_TOKENS_PER_CALL]
            try:
                response = await asyncio.to_thread(
                    messaging.send_each_for_multicast, self._build(batch, message), app=self.app
                )
            except firebase_exceptions.FirebaseError as exc:
                logger.warning("FCM request failed: %s", exc)
                result.failure_count += len(batch)
                result.error = str(exc)
                result.retryable = True
                continue
            for token, item in zip(batch, response.responses, strict=True):
                if item.success:
                    result.success_count += 1
                    continue
                result.failure_count += 1
                exc = item.exception
                # Only drop tokens FCM says are permanently dead (permission revoked etc.).
                if isinstance(exc, messaging.UnregisteredError | messaging.SenderIdMismatchError):
                    result.invalid_tokens.append(token)
                else:
                    result.error = str(exc)
                    result.retryable = result.retryable or not isinstance(
                        exc, firebase_exceptions.InvalidArgumentError
                    )
        if result.success_count == 0 and result.error is None and result.invalid_tokens:
            result.error = "All registered devices have expired; enable notifications again"
        return result
