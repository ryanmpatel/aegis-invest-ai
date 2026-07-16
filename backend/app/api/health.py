"""Health and system-status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app as app_pkg
from app.api.deps import current_user, get_broker
from app.config import Settings, get_settings
from app.database import get_db
from app.services.risk.events import is_trading_frozen
from app.services.risk.kill_switch import get_kill_switch_state
from app.utils.timeutils import utcnow
from app.workers.scheduler import next_run_time

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_db)) -> dict:
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "version": app_pkg.__version__,
        "time": utcnow().isoformat(),
    }


@router.get("/system/status")
async def system_status(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    username: str = Depends(current_user),
    broker=Depends(get_broker),
) -> dict:
    kill_switch = await get_kill_switch_state(session)
    frozen, frozen_reason = await is_trading_frozen(session)
    broker_ok = True
    market_open = None
    try:
        clock = await broker.get_market_clock()
        market_open = clock.is_open
    except Exception:
        broker_ok = False
    return {
        "mode": "paper",
        "live_trading_enabled": False,  # permanently disabled in this build
        "broker_provider": settings.broker_provider,
        "market_data_provider": settings.market_data_provider,
        "ai_provider": settings.ai_provider,
        "broker_reachable": broker_ok,
        "market_open": market_open,
        "kill_switch_active": bool(kill_switch and kill_switch.active),
        "kill_switch_reason": kill_switch.reason if kill_switch else "",
        "trading_frozen": frozen,
        "frozen_reason": frozen_reason,
        "scheduler_enabled": settings.scheduler_enabled,
        "next_scheduled_run": next_run_time(),
    }
