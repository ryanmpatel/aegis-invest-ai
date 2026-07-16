"""Paper-trading control: start/stop scheduler, run-once, status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import csrf_protect, current_user, get_broker, get_market_data
from app.config import Settings, get_settings
from app.database import get_db
from app.models.config import SchedulerConfig
from app.models.trading import StrategyRun
from app.services.ai_analysis.overlay import make_ai_overlay
from app.services.execution.rebalance import RebalanceAborted, RebalanceWorkflow
from app.services.risk.events import is_trading_frozen
from app.services.risk.kill_switch import is_kill_switch_active
from app.services.strategies.registry import build_strategy
from app.utils.timeutils import utcnow
from app.workers.scheduler import next_run_time

router = APIRouter(
    prefix="/api/paper-trading",
    tags=["paper-trading"],
    dependencies=[Depends(current_user)],
)


async def _get_scheduler_config(session: AsyncSession) -> SchedulerConfig:
    config = (await session.execute(select(SchedulerConfig).limit(1))).scalar_one_or_none()
    if config is None:
        config = SchedulerConfig()
        session.add(config)
        await session.flush()
    return config


@router.post("/start", dependencies=[Depends(csrf_protect)])
async def start_paper_trading(session: AsyncSession = Depends(get_db)) -> dict:
    if await is_kill_switch_active(session):
        raise HTTPException(409, "Kill switch is active; deactivate it first.")
    frozen, reason = await is_trading_frozen(session)
    if frozen:
        raise HTTPException(409, f"Trading is frozen: {reason}. Reactivate first.")
    config = await _get_scheduler_config(session)
    config.enabled = True
    config.updated_at = utcnow()
    await session.commit()
    return {"enabled": True}


@router.post("/stop", dependencies=[Depends(csrf_protect)])
async def stop_paper_trading(session: AsyncSession = Depends(get_db)) -> dict:
    config = await _get_scheduler_config(session)
    config.enabled = False
    config.updated_at = utcnow()
    await session.commit()
    return {"enabled": False}


@router.post("/run-once", dependencies=[Depends(csrf_protect)])
async def run_once(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    broker=Depends(get_broker),
    market_data=Depends(get_market_data),
) -> dict:
    """Execute one full paper-trading rebalance now (human-initiated)."""
    workflow = RebalanceWorkflow(
        session=session, settings=settings, broker=broker, market_data=market_data,
        strategy=build_strategy("weekly_multi_factor_trend"),
        ai_overlay=make_ai_overlay(settings.ai_min_confidence),
    )
    try:
        result = await workflow.run(mode="paper", actor="api_run_once")
    except RebalanceAborted as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "strategy_run_id": result.strategy_run_id,
        "status": result.status,
        "submitted_orders": result.submitted_orders,
        "rejected_trades": result.rejected_trades,
    }


@router.get("/status")
async def paper_trading_status(session: AsyncSession = Depends(get_db)) -> dict:
    config = await _get_scheduler_config(session)
    frozen, reason = await is_trading_frozen(session)
    last_run = (
        await session.execute(
            select(StrategyRun)
            .where(StrategyRun.mode == "paper")
            .order_by(StrategyRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    await session.commit()
    return {
        "enabled": config.enabled,
        "trading_allowed": config.trading_allowed,
        "frozen": frozen,
        "frozen_reason": reason,
        "rebalance_cron": config.rebalance_cron,
        "next_scheduled_run": next_run_time(),
        "kill_switch_active": await is_kill_switch_active(session),
        "last_run": (
            {
                "id": str(last_run.id),
                "status": last_run.status,
                "as_of": last_run.as_of.isoformat() if last_run.as_of else None,
                "error": last_run.error,
            }
            if last_run else None
        ),
    }
