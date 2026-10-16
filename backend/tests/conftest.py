"""Shared test setup.

Tests use a separate database (TEST_DATABASE_URL) and Redis db (TEST_REDIS_URL).
The schema is built by running the real Alembic migrations, so migrations are tested too.
Run inside Docker:  docker compose run --rm api pytest
"""

import os

# Must be set before app modules read settings.
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_DEV_MODE"] = "true"
os.environ["FIREBASE_CREDENTIALS_FILE"] = ""

import subprocess  # noqa: E402
import sys  # noqa: E402
from collections.abc import AsyncIterator, Callable  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Instrument, User  # noqa: E402
from app.schemas.market import Quote  # noqa: E402
from app.services.notifier.base import PushMessage, SendResult  # noqa: E402
from app.services.price_cache import PriceCache, create_redis  # noqa: E402

get_settings.cache_clear()
BACKEND_DIR = Path(__file__).resolve().parent.parent


class FakeNotifier:
    """Records what would be pushed. Behaves like FcmNotifier for empty token lists."""

    channel = "fcm"

    def __init__(self) -> None:
        self.sent: list[tuple[list[str], PushMessage]] = []
        self.responder: Callable[[list[str]], SendResult] | None = None

    async def send(self, tokens: list[str], message: PushMessage) -> SendResult:
        self.sent.append((list(tokens), message))
        if self.responder is not None:
            return self.responder(tokens)
        if not tokens:
            return SendResult(error="No devices registered for push notifications")
        return SendResult(success_count=len(tokens))


def make_quote(ltp: float, symbol: str = "NIFTY50", status: str = "open") -> Quote:
    now = datetime.now(UTC)
    return Quote(
        symbol=symbol,
        name="NIFTY 50",
        ltp=ltp,
        open=22500.0,
        high=max(ltp, 22600.0),
        low=min(ltp, 22450.0),
        prev_close=22500.0,
        exchange_ts=now,
        received_at=now,
        source="mock",
        market_status=status,
    ).with_derived_change()


def _alembic(*args: str, db_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={db_url}", *args],
        cwd=BACKEND_DIR,
        check=True,
    )


@pytest.fixture(scope="session")
def settings() -> Settings:
    current = get_settings()
    if not current.test_database_url or not current.test_redis_url:
        pytest.exit("Set TEST_DATABASE_URL and TEST_REDIS_URL (see .env.example)")
    return current


@pytest.fixture(scope="session")
def database_url(settings: Settings) -> str:
    url = settings.test_database_url or ""
    # Down then up: proves both directions of every migration work.
    _alembic("downgrade", "base", db_url=url)
    _alembic("upgrade", "head", db_url=url)
    return url


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    test_engine = create_async_engine(database_url, poolclass=NullPool)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """A clean database for each test that needs one (pure unit tests skip the DB)."""
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE notifications, device_tokens, alerts, users RESTART IDENTITY CASCADE")
        )
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def redis(settings: Settings) -> AsyncIterator[Redis]:
    client = create_redis(settings.test_redis_url or "")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def cache(redis: Redis) -> PriceCache:
    return PriceCache(redis)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
async def client(
    settings: Settings, session_factory: async_sessionmaker, redis: Redis, notifier: FakeNotifier
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, session_factory=session_factory, redis=redis, notifier=notifier)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            http.app = app  # type: ignore[attr-defined]
            yield http


def auth(email: str = "alice@example.com") -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{email}"}


@pytest.fixture
async def nifty_id(session_factory: async_sessionmaker) -> int:
    async with session_factory() as session:
        return (
            await session.scalar(select(Instrument.id).where(Instrument.symbol == "NIFTY50"))
        ) or 0


@pytest.fixture
async def user(session_factory: async_sessionmaker) -> User:
    async with session_factory() as session:
        created = User(firebase_uid="dev:bob@example.com", email="bob@example.com")
        session.add(created)
        await session.commit()
        return created
