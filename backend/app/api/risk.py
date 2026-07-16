"""Risk, signals, decisions, kill switch, and activity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import csrf_protect, current_user, get_broker
from app.database import get_db
from app.models.trading import (
    Fill,
    Order,
    ProposedTrade,
    RiskDecision,
    RiskEvent,
    Signal,
    StrategyRun,
)
from app.services.execution.engine import ExecutionEngine
from app.services.risk.events import reactivate_trading
from app.services.risk.kill_switch import get_kill_switch_state, set_kill_switch

router = APIRouter(prefix="/api", tags=["risk"], dependencies=[Depends(current_user)])


@router.get("/signals")
async def list_signals(
    session: AsyncSession = Depends(get_db), run_id: str | None = None, limit: int = 200
) -> list[dict]:
    query = select(Signal).order_by(Signal.created_at.desc()).limit(min(limit, 1000))
    if run_id:
        import uuid

        query = query.where(Signal.strategy_run_id == uuid.UUID(run_id))
    rows = (await session.execute(query)).scalars().all()
    return [
        {
            "id": str(r.id),
            "strategy_run_id": str(r.strategy_run_id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "symbol": r.symbol,
            "eligible": r.eligible,
            "exclusion_reasons": r.exclusion_reasons,
            "indicators": r.indicators,
            "score": r.score,
            "score_breakdown": r.score_breakdown,
        }
        for r in rows
    ]


@router.get("/decisions")
async def list_decisions(
    session: AsyncSession = Depends(get_db), limit: int = 200
) -> list[dict]:
    rows = (
        await session.execute(
            select(RiskDecision, ProposedTrade)
            .join(ProposedTrade, RiskDecision.proposed_trade_id == ProposedTrade.id)
            .order_by(RiskDecision.created_at.desc())
            .limit(min(limit, 1000))
        )
    ).all()
    return [
        {
            "id": str(d.id),
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "strategy_run_id": str(d.strategy_run_id),
            "symbol": t.symbol,
            "side": t.side,
            "proposed_notional": t.notional,
            "decision": d.decision,
            "approved_notional": d.approved_notional,
            "rule_name": d.rule_name,
            "actual_value": d.actual_value,
            "limit_value": d.limit_value,
            "message": (d.details or {}).get("message", ""),
        }
        for d, t in rows
    ]


@router.get("/risk/events")
async def list_risk_events(
    session: AsyncSession = Depends(get_db), limit: int = 200
) -> list[dict]:
    rows = (
        await session.execute(
            select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(min(limit, 1000))
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "severity": r.severity,
            "rule_name": r.rule_name,
            "message": r.message,
            "actual_value": r.actual_value,
            "limit_value": r.limit_value,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
        for r in rows
    ]


@router.get("/risk/status")
async def risk_status(session: AsyncSession = Depends(get_db)) -> dict:
    from app.services.risk.events import is_trading_frozen

    kill = await get_kill_switch_state(session)
    frozen, reason = await is_trading_frozen(session)
    open_events = (
        await session.execute(
            select(RiskEvent)
            .where(RiskEvent.severity == "critical", RiskEvent.resolved_at.is_(None))
            .order_by(RiskEvent.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return {
        "kill_switch_active": bool(kill and kill.active),
        "trading_frozen": frozen,
        "frozen_reason": reason,
        "open_critical_events": [
            {"rule_name": e.rule_name, "message": e.message,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in open_events
        ],
    }


@router.post("/risk/reactivate", dependencies=[Depends(csrf_protect)])
async def reactivate(
    session: AsyncSession = Depends(get_db), username: str = Depends(current_user)
) -> dict:
    await reactivate_trading(session, actor=username)
    await session.commit()
    return {"trading_allowed": True}


class KillSwitchRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/kill-switch/activate", dependencies=[Depends(csrf_protect)])
async def activate_kill_switch(
    body: KillSwitchRequest,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(current_user),
    broker=Depends(get_broker),
) -> dict:
    event = await set_kill_switch(session, active=True, actor=username, reason=body.reason)
    # Cancel open buy orders immediately; positions are left unchanged.
    canceled = 0
    try:
        engine = ExecutionEngine(broker, session)
        canceled = await engine.cancel_open_buy_orders()
    except Exception:
        pass  # broker unreachable: the switch still blocks all submissions
    await session.commit()
    return {"active": True, "canceled_buy_orders": canceled, "event_id": str(event.id)}


@router.post("/kill-switch/deactivate", dependencies=[Depends(csrf_protect)])
async def deactivate_kill_switch(
    body: KillSwitchRequest,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(current_user),
) -> dict:
    event = await set_kill_switch(session, active=False, actor=username, reason=body.reason)
    await session.commit()
    return {"active": False, "event_id": str(event.id)}


@router.get("/activity")
async def activity_log(
    session: AsyncSession = Depends(get_db), limit: int = 100
) -> list[dict]:
    """Chronological audit feed across runs, decisions, orders, fills, events."""
    limit = min(limit, 500)
    entries: list[dict] = []

    runs = (
        await session.execute(
            select(StrategyRun).order_by(StrategyRun.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    entries += [
        {
            "type": "strategy_run",
            "at": r.created_at.isoformat() if r.created_at else None,
            "summary": f"{r.strategy_name} v{r.strategy_version} ({r.mode}) — {r.status}",
            "detail": {"id": str(r.id), "error": r.error},
        }
        for r in runs
    ]
    orders = (
        await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    entries += [
        {
            "type": "order",
            "at": o.created_at.isoformat() if o.created_at else None,
            "summary": f"{o.side.upper()} {o.quantity:g} {o.symbol} — {o.status}",
            "detail": {"client_order_id": o.client_order_id},
        }
        for o in orders
    ]
    fills = (
        await session.execute(select(Fill).order_by(Fill.created_at.desc()).limit(limit))
    ).scalars().all()
    entries += [
        {
            "type": "fill",
            "at": f.created_at.isoformat() if f.created_at else None,
            "summary": f"Filled {f.side} {f.quantity:g} {f.symbol} @ {f.price:.2f}",
            "detail": {},
        }
        for f in fills
    ]
    events = (
        await session.execute(
            select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    entries += [
        {
            "type": "risk_event",
            "at": e.created_at.isoformat() if e.created_at else None,
            "summary": f"[{e.severity}] {e.rule_name}: {e.message[:120]}",
            "detail": {},
        }
        for e in events
    ]
    entries.sort(key=lambda item: item["at"] or "", reverse=True)
    return entries[:limit]
