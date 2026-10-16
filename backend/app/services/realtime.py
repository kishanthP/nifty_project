"""Pushes live prices and alert events to browsers over WebSocket.

Each API process keeps ONE Redis subscription and fans messages out to its own
connected browsers. Run more API processes and each does the same, so this scales
horizontally.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.services.price_cache import ALERTS_CHANNEL, QUOTES_CHANNEL

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 5.0


@dataclass(eq=False)
class Client:
    websocket: WebSocket
    user_id: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, text: str) -> None:
        # The hub and the connection handler both send; never interleave frames.
        async with self._lock:
            await self.websocket.send_text(text)


class RealtimeHub:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.clients: set[Client] = set()
        self._task: asyncio.Task | None = None

    def register(self, websocket: WebSocket) -> Client:
        client = Client(websocket=websocket)
        self.clients.add(client)
        return client

    def unregister(self, client: Client) -> None:
        self.clients.discard(client)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen_forever())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _listen_forever(self) -> None:
        delay = 1.0
        while True:
            try:
                async with self.redis.pubsub() as pubsub:
                    await pubsub.subscribe(QUOTES_CHANNEL, ALERTS_CHANNEL)
                    delay = 1.0
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        await self._route(message["channel"], message["data"])
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError) as exc:
                logger.warning(
                    "Realtime Redis subscription lost (%s); retrying in %.0fs", exc, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
            except Exception:
                logger.exception("Realtime hub error; restarting subscription")
                await asyncio.sleep(delay)

    async def _route(self, channel: str, data: str) -> None:
        if channel == QUOTES_CHANNEL:
            # data is already JSON; wrap it without decoding and re-encoding.
            await self._send_many(self.clients, f'{{"type":"quote","data":{data}}}')
        elif channel == ALERTS_CHANNEL:
            event = json.loads(data)
            user_id = event.get("user_id")
            targets = {c for c in self.clients if c.user_id and str(c.user_id) == user_id}
            if targets:
                await self._send_many(
                    targets, json.dumps({"type": "alert_triggered", "data": event})
                )

    async def _send_many(self, clients: set[Client], text: str) -> None:
        if not clients:
            return
        targets = list(clients)
        results = await asyncio.gather(
            *(asyncio.wait_for(c.send(text), _SEND_TIMEOUT) for c in targets),
            return_exceptions=True,
        )
        for client, result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                # Slow or disconnected browser: drop it; it will reconnect.
                self.unregister(client)
                with contextlib.suppress(Exception):
                    await client.websocket.close()
