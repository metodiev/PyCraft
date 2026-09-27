"""Async engine / session management."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    """Build an async engine for the configured database URL."""
    kwargs: dict[str, object] = {"echo": settings.db_echo, "future": True}
    if not settings.is_sqlite:
        kwargs |= {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_pool_size,
            "pool_pre_ping": True,
        }
    return create_async_engine(settings.database_url, **kwargs)


def init_engine(settings: Settings) -> AsyncEngine:
    """Initialise the process-wide engine and session factory."""
    global _engine, _session_factory
    _engine = create_engine(settings)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:  # pragma: no cover - defensive, lifespan always inits first
        raise RuntimeError("Database engine has not been initialised")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:  # pragma: no cover
        raise RuntimeError("Database session factory has not been initialised")
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with get_session_factory()() as session:
        yield session
