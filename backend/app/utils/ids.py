"""ID helpers: UUIDs and deterministic idempotency keys."""

from __future__ import annotations

import hashlib
import uuid


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def idempotency_key(strategy_run_id: str, symbol: str, side: str, sequence: int = 0) -> str:
    """Deterministic client order id: the same run never submits the same
    trade twice, and retries reuse the same key so the broker can dedupe."""
    raw = f"{strategy_run_id}:{symbol}:{side}:{sequence}"
    return f"aegis-{hashlib.sha256(raw.encode()).hexdigest()[:32]}"
