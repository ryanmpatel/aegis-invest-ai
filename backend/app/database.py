"""Async SQLAlchemy engine/session management."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def normalize_database_url(url: str, *, driver: str = "asyncpg") -> str:
    """Accept Heroku/Neon/Render-style Postgres URLs as pasted.

    - ``postgres://`` → ``postgresql://`` (SQLAlchemy rejects the former)
    - async driver: add ``+asyncpg`` and translate libpq-style query params
      (``sslmode`` → ``ssl``; drop ``channel_binding``, which asyncpg lacks)
    - sync driver (Alembic): strip async driver suffixes and translate
      ``ssl`` back to libpq's ``sslmode``.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")

    if driver == "sync":
        url = url.replace("+asyncpg", "").replace("+aiosqlite", "")
        if url.startswith("postgresql://"):
            parts = urlsplit(url)
            query = dict(parse_qsl(parts.query))
            if "ssl" in query:
                query.setdefault("sslmode", query.pop("ssl"))
            url = urlunsplit(parts._replace(query=urlencode(query)))
        return url

    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        if "sslmode" in query:
            query.setdefault("ssl", query.pop("sslmode"))
        query.pop("channel_binding", None)
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = normalize_database_url(settings.database_url)
        kwargs: dict = {"echo": False, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs.pop("pool_pre_ping")
        if os.environ.get("VERCEL"):
            # Serverless: connections must not outlive the invocation.
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
        _engine = create_async_engine(url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def override_engine(engine: AsyncEngine) -> None:
    """Used by tests to point the app at a temporary database."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)
