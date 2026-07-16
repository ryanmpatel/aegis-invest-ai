"""Backtest endpoints: create, list, detail, trades, equity curve, CSV export."""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import csrf_protect, current_user, get_market_data
from app.database import get_db
from app.models.backtesting import BacktestDailyResult, BacktestRun, BacktestTrade
from app.services.backtesting.runner import make_config, run_backtest

router = APIRouter(
    prefix="/api/backtests",
    tags=["backtests"],
    dependencies=[Depends(current_user)],
)


class BacktestCreate(BaseModel):
    strategy_name: str = "weekly_multi_factor_trend"
    strategy_parameters: dict = Field(default_factory=dict)
    start: str
    end: str
    starting_capital: float = 100_000.0
    universe: list[str] = Field(default_factory=list)
    benchmark_symbol: str | None = "SPY"
    rebalance_frequency: str = "weekly"
    commission_per_trade: float = 0.0
    spread_bps: float = 2.0
    slippage_bps: float = 5.0
    risk_free_annual: float = 0.0


def _parse_run_id(backtest_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(backtest_id)
    except ValueError as exc:
        raise HTTPException(404, "Backtest not found.") from exc


@router.post("", dependencies=[Depends(csrf_protect)])
async def create_backtest(
    body: BacktestCreate,
    session: AsyncSession = Depends(get_db),
    market_data=Depends(get_market_data),
) -> dict:
    try:
        config = make_config(body.model_dump())
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        run = await run_backtest(
            session, market_data,
            strategy_name=body.strategy_name,
            strategy_parameters=body.strategy_parameters or None,
            config=config,
        )
        await session.commit()
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        await session.commit()  # persist the failed-run record
        raise HTTPException(500, f"Backtest failed: {exc}") from exc
    return {"id": str(run.id), "status": run.status, "metrics": run.metrics,
            "warnings": run.warnings}


@router.get("")
async def list_backtests(session: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await session.execute(
            select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(100)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "strategy_name": r.strategy_name,
            "strategy_version": r.strategy_version,
            "status": r.status,
            "parameters": r.parameters,
            "total_return": (r.metrics or {}).get("total_return"),
            "max_drawdown": (r.metrics or {}).get("max_drawdown"),
        }
        for r in rows
    ]


@router.get("/{backtest_id}")
async def get_backtest(backtest_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    run = (
        await session.execute(
            select(BacktestRun).where(BacktestRun.id == _parse_run_id(backtest_id))
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Backtest not found.")
    return {
        "id": str(run.id),
        "status": run.status,
        "error": run.error,
        "strategy_name": run.strategy_name,
        "strategy_version": run.strategy_version,
        "parameters": run.parameters,
        "metrics": run.metrics,
        "warnings": run.warnings,
    }


@router.get("/{backtest_id}/trades")
async def get_trades(
    backtest_id: str,
    session: AsyncSession = Depends(get_db),
    export: str | None = None,
):
    rows = (
        await session.execute(
            select(BacktestTrade)
            .where(BacktestTrade.backtest_run_id == _parse_run_id(backtest_id))
            .order_by(BacktestTrade.trade_date)
        )
    ).scalars().all()
    records = [
        {
            "date": r.trade_date.isoformat(),
            "symbol": r.symbol,
            "side": r.side,
            "quantity": round(r.quantity, 6),
            "price": round(r.price, 4),
            "commission": r.commission,
            "slippage_cost": round(r.slippage_cost, 4),
            "reason": r.reason,
        }
        for r in rows
    ]
    if export == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=["date", "symbol", "side", "quantity", "price",
                        "commission", "slippage_cost", "reason"],
        )
        writer.writeheader()
        writer.writerows(records)
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    f"attachment; filename=backtest_{backtest_id}_trades.csv"
            },
        )
    return records


@router.get("/{backtest_id}/equity")
async def get_equity(
    backtest_id: str, session: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = (
        await session.execute(
            select(BacktestDailyResult)
            .where(BacktestDailyResult.backtest_run_id == _parse_run_id(backtest_id))
            .order_by(BacktestDailyResult.result_date)
        )
    ).scalars().all()
    return [
        {
            "date": r.result_date.isoformat(),
            "equity": r.equity,
            "cash": r.cash,
            "invested_value": r.invested_value,
            "daily_return": r.daily_return,
            "drawdown": r.drawdown,
            "benchmark_equity": r.benchmark_equity,
        }
        for r in rows
    ]
