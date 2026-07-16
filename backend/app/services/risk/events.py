"""Risk-event recording and account-limit response.

When an account-level limit is hit: cancel pending buys, block new purchases,
record a critical risk event, disable the scheduler, require manual
reactivation. Positions are never auto-liquidated unless the user explicitly
enables that behavior.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.config import SchedulerConfig
from app.models.trading import RiskEvent
from app.schemas.risk import RuleCheck
from app.utils.timeutils import utcnow

logger = get_logger("risk.events")


async def record_risk_event(
    session: AsyncSession,
    *,
    severity: str,
    rule_name: str,
    message: str,
    correlation_id: str = "",
    actual_value: float | None = None,
    limit_value: float | None = None,
    details: dict | None = None,
) -> RiskEvent:
    event = RiskEvent(
        severity=severity,
        rule_name=rule_name,
        message=message,
        correlation_id=correlation_id,
        actual_value=actual_value,
        limit_value=limit_value,
        details=details or {},
    )
    session.add(event)
    await session.flush()
    log_event(
        logger, "risk_event", message,
        rule_name=rule_name, risk_severity=severity,
        actual_value=actual_value, limit_value=limit_value,
    )
    return event


async def freeze_trading(
    session: AsyncSession, *, reason: str, correlation_id: str = "",
    failed_checks: list[RuleCheck] | None = None,
) -> None:
    """Disable the trading scheduler until a human re-enables it."""
    config = (
        await session.execute(select(SchedulerConfig).limit(1))
    ).scalar_one_or_none()
    if config is None:
        config = SchedulerConfig()
        session.add(config)
    config.trading_allowed = False
    config.frozen_reason = reason
    config.updated_at = utcnow()
    await session.flush()
    await record_risk_event(
        session, severity="critical", rule_name="trading_frozen",
        message=f"Trading frozen: {reason}", correlation_id=correlation_id,
        details={
            "failed_checks": [c.model_dump() for c in (failed_checks or [])],
        },
    )


async def is_trading_frozen(session: AsyncSession) -> tuple[bool, str]:
    config = (
        await session.execute(select(SchedulerConfig).limit(1))
    ).scalar_one_or_none()
    if config is None:
        return False, ""
    return (not config.trading_allowed), config.frozen_reason


async def reactivate_trading(session: AsyncSession, *, actor: str) -> None:
    """Manual reactivation after a freeze."""
    config = (
        await session.execute(select(SchedulerConfig).limit(1))
    ).scalar_one_or_none()
    if config is None:
        return
    config.trading_allowed = True
    config.frozen_reason = ""
    config.updated_at = utcnow()
    await session.flush()
    await record_risk_event(
        session, severity="info", rule_name="trading_reactivated",
        message=f"Trading manually reactivated by {actor}",
    )
