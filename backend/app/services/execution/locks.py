"""Distributed locks for single-flight rebalances.

Redis ``SET NX PX`` when available; a process-local fallback for development
(guarded by ALLOW_LOCAL_LOCK_FALLBACK). Duplicate acquisition raises
LockNotAcquiredError, which the rebalance workflow treats as a freeze
condition ("same job runs twice").
"""

from __future__ import annotations

import asyncio
import secrets
from types import TracebackType
from typing import Any

from app.config import Settings
from app.logging import get_logger, log_event

logger = get_logger("execution.locks")


class LockNotAcquiredError(Exception):
    pass


class LocalLock:
    """Process-local async lock registry (dev/test fallback)."""

    _locks: dict[str, str] = {}  # noqa: RUF012 - intentional process-global registry
    _guard = asyncio.Lock()

    def __init__(self, key: str, ttl_seconds: int = 600) -> None:
        self.key = key
        self.ttl = ttl_seconds
        self._token = secrets.token_hex(8)

    async def __aenter__(self) -> LocalLock:
        async with LocalLock._guard:
            if self.key in LocalLock._locks:
                raise LockNotAcquiredError(f"lock {self.key} already held")
            LocalLock._locks[self.key] = self._token
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        async with LocalLock._guard:
            if LocalLock._locks.get(self.key) == self._token:
                del LocalLock._locks[self.key]


class RedisLock:
    def __init__(self, redis_url: str, key: str, ttl_seconds: int = 600) -> None:
        self.redis_url = redis_url
        self.key = f"aegis:lock:{key}"
        self.ttl_ms = ttl_seconds * 1000
        self._token = secrets.token_hex(16)
        self._client: Any = None

    async def __aenter__(self) -> RedisLock:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(self.redis_url)
        acquired = await self._client.set(self.key, self._token, nx=True, px=self.ttl_ms)
        if not acquired:
            await self._client.aclose()
            raise LockNotAcquiredError(f"lock {self.key} already held")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is None:
            return
        # Release only if we still own it (compare-and-delete).
        release_script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            await self._client.eval(release_script, 1, self.key, self._token)
        finally:
            await self._client.aclose()


def rebalance_lock(settings: Settings, key: str = "rebalance", ttl_seconds: int = 900):
    """Return the best available lock context manager."""
    try:
        import redis.asyncio  # noqa: F401

        return RedisLock(settings.redis_url, key, ttl_seconds)
    except ImportError:
        pass
    if not settings.allow_local_lock_fallback:
        raise RuntimeError("Redis unavailable and local lock fallback is disabled.")
    log_event(logger, "lock_fallback", "Using process-local lock (Redis unavailable)")
    return LocalLock(key, ttl_seconds)


async def acquire_lock_or_raise(settings: Settings, key: str, ttl_seconds: int = 900):
    """Helper that prefers Redis but falls back to LocalLock when Redis cannot
    be reached at runtime (connection error), if allowed by settings."""
    lock = rebalance_lock(settings, key, ttl_seconds)
    try:
        await lock.__aenter__()
        return lock
    except LockNotAcquiredError:
        raise
    except Exception as exc:
        if isinstance(lock, RedisLock) and settings.allow_local_lock_fallback:
            log_event(
                logger, "lock_fallback",
                f"Redis lock failed ({exc.__class__.__name__}); using local lock",
            )
            fallback = LocalLock(key, ttl_seconds)
            await fallback.__aenter__()
            return fallback
        raise
