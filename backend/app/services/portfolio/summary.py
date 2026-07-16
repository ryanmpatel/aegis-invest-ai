"""Dashboard summary calculations from stored snapshots and broker state."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import AccountSnapshot


async def account_summary(session: AsyncSession) -> dict[str, Any]:
    snapshots = (
        await session.execute(
            select(AccountSnapshot).order_by(AccountSnapshot.created_at.desc()).limit(400)
        )
    ).scalars().all()
    if not snapshots:
        return {
            "equity": None, "cash": None, "buying_power": None,
            "daily_pl": None, "daily_pl_pct": None,
            "total_pl": None, "total_pl_pct": None, "current_drawdown": None,
        }
    latest = snapshots[0]
    oldest = snapshots[-1]
    previous = snapshots[1] if len(snapshots) > 1 else None

    daily_pl = latest.equity - previous.equity if previous else None
    daily_pl_pct = (
        daily_pl / previous.equity if previous and previous.equity > 0 and daily_pl is not None
        else None
    )
    total_pl = latest.equity - oldest.equity
    total_pl_pct = total_pl / oldest.equity if oldest.equity > 0 else None
    peak = max(s.equity for s in snapshots)
    current_drawdown = latest.equity / peak - 1.0 if peak > 0 else None

    return {
        "equity": latest.equity,
        "cash": latest.cash,
        "buying_power": latest.buying_power,
        "daily_pl": daily_pl,
        "daily_pl_pct": daily_pl_pct,
        "total_pl": total_pl,
        "total_pl_pct": total_pl_pct,
        "current_drawdown": current_drawdown,
        "as_of": latest.created_at.isoformat(),
    }
