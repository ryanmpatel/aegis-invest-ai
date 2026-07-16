"""Settings endpoints: universe, risk limits, schedule. Credentials are set
via environment variables only and are never returned to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import csrf_protect, current_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models.config import ApprovedUniverse, RiskProfile, SchedulerConfig
from app.schemas.risk import RiskLimits
from app.utils.timeutils import utcnow

router = APIRouter(
    prefix="/api/settings", tags=["settings"], dependencies=[Depends(current_user)]
)

MAX_UNIVERSE_SIZE = 50


class UniverseUpdate(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=MAX_UNIVERSE_SIZE)


@router.get("/universe")
async def get_universe(session: AsyncSession = Depends(get_db)) -> dict:
    row = (
        await session.execute(
            select(ApprovedUniverse).where(ApprovedUniverse.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    return {
        "name": row.name if row else None,
        "symbols": row.symbols if row else [],
    }


@router.put("/universe", dependencies=[Depends(csrf_protect)])
async def update_universe(
    body: UniverseUpdate, session: AsyncSession = Depends(get_db)
) -> dict:
    symbols = sorted({s.strip().upper() for s in body.symbols if s.strip()})
    if not symbols:
        raise HTTPException(422, "Universe cannot be empty.")
    for symbol in symbols:
        if not symbol.isalnum() or len(symbol) > 10:
            raise HTTPException(422, f"Invalid symbol: {symbol!r}")
    row = (
        await session.execute(
            select(ApprovedUniverse).where(ApprovedUniverse.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = ApprovedUniverse(name="default", is_active=True)
        session.add(row)
    row.symbols = symbols
    row.updated_at = utcnow()
    await session.commit()
    return {"symbols": symbols}


@router.get("/risk-limits")
async def get_risk_limits(session: AsyncSession = Depends(get_db)) -> dict:
    profile = (
        await session.execute(
            select(RiskProfile).where(RiskProfile.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    defaults = RiskLimits().model_dump()
    if profile is None:
        return {"name": "defaults", "limits": defaults}
    return {"name": profile.name, "limits": {**defaults, **profile.limits}}


@router.put("/risk-limits", dependencies=[Depends(csrf_protect)])
async def update_risk_limits(
    body: dict, session: AsyncSession = Depends(get_db)
) -> dict:
    try:
        validated = RiskLimits(**{**RiskLimits().model_dump(), **body})
    except ValidationError as exc:
        raise HTTPException(422, f"Invalid risk limits: {exc}") from exc
    if validated.allow_leverage or validated.allow_shorting:
        raise HTTPException(422, "Leverage and shorting cannot be enabled.")
    profile = (
        await session.execute(
            select(RiskProfile).where(RiskProfile.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = RiskProfile(name="custom", is_active=True)
        session.add(profile)
    profile.limits = validated.model_dump()
    await session.commit()
    return {"limits": profile.limits}


class ScheduleUpdate(BaseModel):
    rebalance_cron: str = Field(min_length=9, max_length=64)


@router.put("/schedule", dependencies=[Depends(csrf_protect)])
async def update_schedule(
    body: ScheduleUpdate, session: AsyncSession = Depends(get_db)
) -> dict:
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(body.rebalance_cron, timezone="UTC")
    except ValueError as exc:
        raise HTTPException(422, f"Invalid cron expression: {exc}") from exc
    config = (await session.execute(select(SchedulerConfig).limit(1))).scalar_one_or_none()
    if config is None:
        config = SchedulerConfig()
        session.add(config)
    config.rebalance_cron = body.rebalance_cron
    config.updated_at = utcnow()
    await session.commit()
    return {"rebalance_cron": body.rebalance_cron,
            "note": "Restart the backend for the scheduler to pick up the new cron."}


@router.get("/providers")
async def provider_status(settings: Settings = Depends(get_settings)) -> dict:
    """Provider configuration status. Secrets are never included."""
    return {
        "broker_provider": settings.broker_provider,
        "market_data_provider": settings.market_data_provider,
        "ai_provider": settings.ai_provider,
        "alpaca_credentials_present": bool(
            settings.alpaca_paper_api_key.get_secret_value()
        ),
        "ai_key_present": bool(settings.ai_api_key.get_secret_value()),
        "live_trading_enabled": False,
    }
