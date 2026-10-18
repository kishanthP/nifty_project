from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def create_engine(database_url: str, pool_size: int = 10, max_overflow: int = 20) -> AsyncEngine:
    return create_async_engine(
        database_url, pool_pre_ping=True, pool_size=pool_size, max_overflow=max_overflow
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


# Creating the engine does not connect yet; connections open on first use.
_settings = get_settings()
engine = create_engine(_settings.database_url, _settings.db_pool_size, _settings.db_max_overflow)
SessionLocal = create_session_factory(engine)
