"""AI risk overlay.

Applies stored AI analyses to a target portfolio. It may ONLY:
- reduce a target weight,
- veto (zero) a proposed buy,
- flag a position for review.
It can never add symbols, increase weights, or create purchases. Missing or
low-confidence analysis is neutral (no adjustment).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.market_data import AINewsAnalysis
from app.schemas.strategy import TargetWeight
from app.utils.timeutils import utcnow

logger = get_logger("ai_analysis.overlay")

ANALYSIS_MAX_AGE_DAYS = 7
REDUCTION_BY_RISK_LEVEL = {"high": 0.5}   # halve weight on high risk
VETO_RISK_LEVELS = {"critical"}


def make_ai_overlay(min_confidence: float):
    """Build the overlay callable used by the rebalance workflow."""

    async def overlay(
        session: AsyncSession, targets: list[TargetWeight], universe: list[str]
    ) -> tuple[list[TargetWeight], list[dict]]:
        adjustments: list[dict] = []
        cutoff = utcnow() - timedelta(days=ANALYSIS_MAX_AGE_DAYS)
        adjusted: list[TargetWeight] = []
        for target in targets:
            latest = (
                await session.execute(
                    select(AINewsAnalysis)
                    .where(
                        AINewsAnalysis.symbol == target.symbol,
                        AINewsAnalysis.created_at >= cutoff,
                    )
                    .order_by(AINewsAnalysis.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            # Missing analysis, or below the confidence bar → neutral.
            if latest is None or latest.confidence < min_confidence:
                adjusted.append(target)
                continue

            if latest.risk_level in VETO_RISK_LEVELS:
                adjustments.append({
                    "symbol": target.symbol, "action": "veto",
                    "risk_level": latest.risk_level,
                    "confidence": latest.confidence,
                    "analysis_id": str(latest.id),
                    "original_weight": target.target_weight,
                    "new_weight": 0.0,
                })
                log_event(
                    logger, "ai_veto",
                    f"AI vetoed buy of {target.symbol} (risk {latest.risk_level})",
                    symbol=target.symbol,
                )
                continue  # dropped entirely (weight goes to cash)

            factor = REDUCTION_BY_RISK_LEVEL.get(latest.risk_level)
            if factor is not None:
                new_weight = round(target.target_weight * factor, 6)
                adjustments.append({
                    "symbol": target.symbol, "action": "reduce",
                    "risk_level": latest.risk_level,
                    "confidence": latest.confidence,
                    "analysis_id": str(latest.id),
                    "original_weight": target.target_weight,
                    "new_weight": new_weight,
                })
                adjusted.append(
                    target.model_copy(update={
                        "target_weight": new_weight,
                        "reasons": [*target.reasons,
                                    f"AI risk reduction ({latest.risk_level})"],
                    })
                )
                continue

            if latest.risk_level == "medium":
                adjustments.append({
                    "symbol": target.symbol, "action": "flag",
                    "risk_level": latest.risk_level,
                    "confidence": latest.confidence,
                    "analysis_id": str(latest.id),
                    "original_weight": target.target_weight,
                    "new_weight": target.target_weight,
                })
            adjusted.append(target)
        return adjusted, adjustments

    return overlay


def build_ai_provider(settings):
    """Factory: mock by default; anthropic only when configured."""
    if settings.ai_provider == "anthropic":
        from app.services.ai_analysis.anthropic_provider import AnthropicAnalysisProvider

        return AnthropicAnalysisProvider(settings)
    from app.services.ai_analysis.mock_provider import MockAIAnalysisProvider

    return MockAIAnalysisProvider()
