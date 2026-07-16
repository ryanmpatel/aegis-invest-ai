"""Retry with exponential backoff for SAFE (read-only, idempotent) calls.

Order submissions must NOT use this helper — an uncertain submission must be
confirmed before any retry (see execution engine).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def retry_async[T](
    fn: Callable[[], T | Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retriable: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Run ``fn`` (sync or async) with exponential backoff.

    Sync callables are dispatched to a thread so blocking SDK clients don't
    stall the event loop.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            if asyncio.iscoroutinefunction(fn):
                return await fn()  # type: ignore[misc, no-any-return]
            result = await asyncio.to_thread(fn)
            if asyncio.iscoroutine(result):
                return await result
            return result  # type: ignore[return-value]
        except retriable as exc:
            last_exc = exc
            if attempt == attempts - 1:
                break
            await asyncio.sleep(min(max_delay, base_delay * (2**attempt)))
    assert last_exc is not None
    raise last_exc
