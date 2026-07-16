"""Kill switch: append-only event log; latest row is authoritative.

When active: no order submission of any kind, scheduler disabled, open buy
orders canceled. Existing positions are left unchanged by default.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.trading import KillSwitchEvent
from app.utils.timeutils import as_utc, utcnow

logger = get_logger("risk.kill_switch")


async def is_kill_switch_active(session: AsyncSession) -> bool:
    latest = (
        await session.execute(
            select(KillSwitchEvent).order_by(KillSwitchEvent.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return bool(latest and latest.active)


async def get_kill_switch_state(session: AsyncSession) -> KillSwitchEvent | None:
    return (
        await session.execute(
            select(KillSwitchEvent).order_by(KillSwitchEvent.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def set_kill_switch(
    session: AsyncSession, *, active: bool, actor: str, reason: str
) -> KillSwitchEvent:
    event = KillSwitchEvent(active=active, actor=actor, reason=reason)
    # Guarantee strict ordering even if two events land on the same clock tick:
    # the new event's timestamp must exceed the previous latest.
    previous = await get_kill_switch_state(session)
    now = utcnow()
    if previous is not None and previous.created_at is not None:
        prev_ts = as_utc(previous.created_at)
        if prev_ts >= now:
            now = prev_ts + timedelta(microseconds=1)
    event.created_at = now
    session.add(event)
    await session.flush()
    log_event(
        logger, "kill_switch_activated" if active else "kill_switch_deactivated",
        f"Kill switch {'ACTIVATED' if active else 'deactivated'} by {actor}: {reason}",
        actor=actor, reason=reason,
    )
    return event
