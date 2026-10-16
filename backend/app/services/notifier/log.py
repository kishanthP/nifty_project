import logging

from app.services.notifier.base import PushMessage, SendResult

logger = logging.getLogger(__name__)


class LogNotifier:
    """Used when Firebase isn't configured: writes notifications to the worker log."""

    channel = "log"

    async def send(self, tokens: list[str], message: PushMessage) -> SendResult:
        logger.info("NOTIFY (%d devices) %s — %s", len(tokens), message.title, message.body)
        return SendResult(success_count=1)
