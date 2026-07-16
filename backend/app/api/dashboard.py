"""Dashboard summary and performance endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_broker
from app.database import get_db
from app.models.trading import AccountSnapshot, StrategyRun, TargetPortfolioRecord
from app.services.portfolio.summary import account_summary
from app.services.risk.kill_switch import is_kill_switch_active

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(current_user)]
)


@router.get("/summary")
async def summary(
    session: AsyncSession = Depends(get_db), broker=Depends(get_broker)
) -> dict:
    stored = await account_summary(session)
    # Prefer live broker numbers when reachable.
    try:
        account = await broker.get_account()
        stored.update(
            equity=account.equity, cash=account.cash, buying_power=account.buying_power
        )
        broker_ok = True
    except Exception:
        broker_ok = False

    active_run = (
        await session.execute(
            select(StrategyRun).order_by(StrategyRun.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return {
        **stored,
        "broker_reachable": broker_ok,
        "kill_switch_active": await is_kill_switch_active(session),
        "active_strategy": (
            {
                "name": active_run.strategy_name,
                "version": active_run.strategy_version,
                "last_run_status": active_run.status,
                "last_run_at": active_run.created_at.isoformat()
                if active_run.created_at else None,
            }
            if active_run else None
        ),
    }


@router.get("/performance")
async def performance(
    session: AsyncSession = Depends(get_db), limit: int = 500
) -> list[dict]:
    rows = (
        await session.execute(
            select(AccountSnapshot)
            .order_by(AccountSnapshot.created_at.asc())
            .limit(min(limit, 2000))
        )
    ).scalars().all()
    return [
        {
            "at": r.created_at.isoformat() if r.created_at else None,
            "equity": r.equity,
            "cash": r.cash,
        }
        for r in rows
    ]


@router.get("/targets")
async def current_targets(session: AsyncSession = Depends(get_db)) -> dict:
    latest = (
        await session.execute(
            select(TargetPortfolioRecord)
            .order_by(TargetPortfolioRecord.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return {"targets": [], "cash_target": None, "ai_adjustments": []}
    return {
        "as_of": latest.as_of.isoformat() if latest.as_of else None,
        "targets": latest.targets,
        "cash_target": latest.cash_target,
        "ai_adjustments": latest.ai_adjustments,
    }
