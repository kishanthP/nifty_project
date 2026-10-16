"""WebSocket: live quotes reach every browser; alert events reach only their owner."""

import json
import time

import redis as sync_redis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.main import create_app
from app.services.price_cache import ALERTS_CHANNEL, QUOTES_CHANNEL
from tests.conftest import FakeNotifier, make_quote


def _wait_for_subscriber(client: sync_redis.Redis, channel: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dict(client.pubsub_numsub(channel)).get(channel, 0) > 0:
            return
        time.sleep(0.05)
    raise AssertionError(f"Nobody subscribed to {channel}")


def test_quotes_and_private_alert_events(settings: Settings, database_url: str) -> None:
    # TestClient runs the app in its own event loop, so the app gets its own connections.
    app_settings = settings.model_copy(update={"redis_url": settings.test_redis_url})
    engine = create_async_engine(database_url, poolclass=NullPool)
    app = create_app(
        app_settings,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        notifier=FakeNotifier(),
    )
    publisher = sync_redis.Redis.from_url(settings.test_redis_url or "", decode_responses=True)

    with TestClient(app) as http:
        with (
            http.websocket_connect("/api/v1/ws/market") as alice,
            http.websocket_connect("/api/v1/ws/market") as guest,
        ):
            alice.send_json({"type": "ping"})
            assert alice.receive_json() == {"type": "pong"}
            alice.send_json({"type": "auth", "token": "dev:alice@example.com"})
            assert alice.receive_json() == {"type": "auth_ok"}
            user_id = http.get(
                "/api/v1/me", headers={"Authorization": "Bearer dev:alice@example.com"}
            ).json()["id"]

            _wait_for_subscriber(publisher, QUOTES_CHANNEL)
            publisher.publish(QUOTES_CHANNEL, make_quote(22561.5).model_dump_json())
            for socket in (alice, guest):
                message = socket.receive_json()
                assert message["type"] == "quote" and message["data"]["ltp"] == 22561.5

            event = {
                "type": "alert_triggered",
                "user_id": user_id,
                "title": "NIFTY 50 rose above 22,560.00",
            }
            publisher.publish(ALERTS_CHANNEL, json.dumps(event))
            received = alice.receive_json()
            assert received["type"] == "alert_triggered"
            assert received["data"]["title"] == event["title"]

            # The guest must not get Alice's alert: the next thing it sees is the next quote.
            publisher.publish(QUOTES_CHANNEL, make_quote(22562).model_dump_json())
            assert guest.receive_json()["data"]["ltp"] == 22562
    publisher.close()
