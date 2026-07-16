"""Strategy endpoints: list, create definitions, activate, preview."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import csrf_protect, current_user, get_broker, get_market_data
from app.config import Settings, get_settings
from app.database import get_db
from app.models.config import StrategyDefinition, StrategyVersion
from app.services.execution.rebalance import RebalanceAborted, RebalanceWorkflow
from app.services.strategies.registry import available_strategies, build_strategy

router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(current_user)],
)


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    engine: str = "weekly_multi_factor_trend"
    parameters: dict = Field(default_factory=dict)


@router.get("")
async def list_strategies(session: AsyncSession = Depends(get_db)) -> dict:
    rows = (await session.execute(select(StrategyDefinition))).scalars().all()
    return {
        "available_engines": available_strategies(),
        "strategies": [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@router.post("", dependencies=[Depends(csrf_protect)])
async def create_strategy(
    body: StrategyCreate, session: AsyncSession = Depends(get_db)
) -> dict:
    if body.engine not in available_strategies():
        raise HTTPException(422, f"Unknown engine {body.engine!r}.")
    existing = (
        await session.execute(
            select(StrategyDefinition).where(StrategyDefinition.name == body.name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "A strategy with this name already exists.")
    definition = StrategyDefinition(name=body.name, description=body.description)
    session.add(definition)
    await session.flush()
    engine = build_strategy(body.engine, body.parameters)
    session.add(
        StrategyVersion(
            definition_id=definition.id,
            version=engine.version,
            parameters={"engine": body.engine, **body.parameters},
        )
    )
    await session.commit()
    return {"id": str(definition.id), "name": definition.name}


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    try:
        key = uuid.UUID(strategy_id)
    except ValueError as exc:
        raise HTTPException(404, "Strategy not found.") from exc
    row = (
        await session.execute(
            select(StrategyDefinition).where(StrategyDefinition.id == key)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Strategy not found.")
    versions = (
        await session.execute(
            select(StrategyVersion).where(StrategyVersion.definition_id == row.id)
        )
    ).scalars().all()
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "is_active": row.is_active,
        "versions": [
            {"version": v.version, "parameters": v.parameters} for v in versions
        ],
    }


@router.post("/{strategy_id}/activate", dependencies=[Depends(csrf_protect)])
async def activate_strategy(
    strategy_id: str, session: AsyncSession = Depends(get_db)
) -> dict:
    try:
        key = uuid.UUID(strategy_id)
    except ValueError as exc:
        raise HTTPException(404, "Strategy not found.") from exc
    rows = (await session.execute(select(StrategyDefinition))).scalars().all()
    target = None
    for row in rows:
        row.is_active = row.id == key
        if row.is_active:
            target = row
    if target is None:
        raise HTTPException(404, "Strategy not found.")
    await session.commit()
    return {"id": str(target.id), "is_active": True}


@router.post("/{strategy_id}/preview", dependencies=[Depends(csrf_protect)])
async def preview_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    broker=Depends(get_broker),
    market_data=Depends(get_market_data),
) -> dict:
    """Run the full pipeline through risk review WITHOUT submitting orders."""
    workflow = RebalanceWorkflow(
        session=session, settings=settings, broker=broker,
        market_data=market_data,
        strategy=build_strategy("weekly_multi_factor_trend"),
    )
    try:
        result = await workflow.run(mode="preview", actor="api_preview")
    except RebalanceAborted as exc:
        raise HTTPException(409, f"Preview aborted: {exc}") from exc
    return {
        "strategy_run_id": result.strategy_run_id,
        "status": result.status,
        "rejected_trades": result.rejected_trades,
        "messages": result.messages,
    }
