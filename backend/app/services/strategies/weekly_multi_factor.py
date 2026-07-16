"""Weekly Multi-Factor Trend Strategy.

An educational, transparent starter strategy — NOT a claim of profitability.

Eligibility: price above 200-day SMA, 50-day SMA above 200-day SMA, liquid,
tradable, complete data, no critical AI risk flag.
Scoring (0..1): medium/long momentum + trend strength - volatility and
drawdown penalties, each component normalized and persisted for explainability.
Sizing: top-N by score, inverse-volatility weights, per-position cap,
remainder held as cash. Rebalances weekly (enforced by the scheduler).
"""

from __future__ import annotations

import math

from app.schemas.strategy import (
    IndicatorSet,
    ScoreBreakdown,
    StrategyContext,
    StrategyResult,
    SymbolEvaluation,
    TargetPortfolio,
    TargetWeight,
)
from app.services.strategies.indicators import compute_indicators

DEFAULT_PARAMETERS: dict[str, float | int] = {
    "min_history_bars": 210,
    "min_avg_dollar_volume": 5_000_000.0,
    "min_price": 5.0,
    "max_positions": 6,
    # Kept at/below the risk engine's max_position_pct so strategy targets are
    # actually achievable and rebalances converge instead of re-proposing.
    "max_position_weight": 0.15,
    "min_score": 0.35,
    "max_price_age_days": 5,
    # score component weights (sum of positive weights = 1)
    "w_momentum_medium": 0.35,
    "w_momentum_long": 0.30,
    "w_trend_strength": 0.35,
    "volatility_penalty_scale": 0.5,
    "drawdown_penalty_scale": 0.5,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _squash(x: float, scale: float) -> float:
    """Map an unbounded value to (0, 1) with a smooth logistic curve."""
    return 1.0 / (1.0 + math.exp(-x / scale))


class WeeklyMultiFactorTrendStrategy:
    name = "weekly_multi_factor_trend"
    version = "1.0.0"

    def __init__(self, parameters: dict | None = None) -> None:
        self.parameters = {**DEFAULT_PARAMETERS, **(parameters or {})}

    # --- eligibility -----------------------------------------------------

    def _check_eligibility(
        self, symbol: str, context: StrategyContext, ind: IndicatorSet, bar_count: int
    ) -> list[str]:
        p = self.parameters
        reasons: list[str] = []
        if not context.tradable.get(symbol, False):
            reasons.append("not_tradable")
        if bar_count < int(p["min_history_bars"]):
            reasons.append(f"insufficient_history ({bar_count} bars)")
        required = (
            ind.latest_price, ind.sma_50, ind.sma_200, ind.realized_vol_21d,
            ind.momentum_63d, ind.momentum_126d, ind.avg_dollar_volume_20d,
            ind.max_drawdown_63d,
        )
        if any(v is None for v in required):
            reasons.append("incomplete_indicator_data")
            return reasons  # cannot evaluate further rules without data
        assert ind.latest_price is not None and ind.sma_50 is not None
        assert ind.sma_200 is not None and ind.avg_dollar_volume_20d is not None
        if ind.latest_price < float(p["min_price"]):
            reasons.append(f"below_min_price ({ind.latest_price:.2f})")
        if ind.avg_dollar_volume_20d < float(p["min_avg_dollar_volume"]):
            reasons.append("insufficient_liquidity")
        if ind.latest_price <= ind.sma_200:
            reasons.append("price_below_200d_sma")
        if ind.sma_50 <= ind.sma_200:
            reasons.append("50d_sma_below_200d_sma")
        if ind.latest_price_date is not None:
            age = (context.as_of.date() - ind.latest_price_date).days
            if age > int(p["max_price_age_days"]):
                reasons.append(f"stale_price_data ({age} days old)")
        if context.ai_risk_flags.get(symbol) == "critical":
            reasons.append("critical_ai_risk_flag")
        return reasons

    # --- scoring ---------------------------------------------------------

    def _score(self, ind: IndicatorSet) -> ScoreBreakdown:
        p = self.parameters
        assert ind.momentum_63d is not None and ind.momentum_126d is not None
        assert ind.latest_price is not None and ind.sma_200 is not None
        assert ind.realized_vol_21d is not None and ind.max_drawdown_63d is not None

        momentum_medium = _squash(ind.momentum_63d, 0.10)
        momentum_long = _squash(ind.momentum_126d, 0.15)
        trend_strength = _squash(ind.latest_price / ind.sma_200 - 1.0, 0.08)
        volatility_penalty = _clamp01(ind.realized_vol_21d / 0.60) * float(
            p["volatility_penalty_scale"]
        )
        drawdown_penalty = _clamp01(abs(ind.max_drawdown_63d) / 0.25) * float(
            p["drawdown_penalty_scale"]
        )
        raw = (
            float(p["w_momentum_medium"]) * momentum_medium
            + float(p["w_momentum_long"]) * momentum_long
            + float(p["w_trend_strength"]) * trend_strength
        )
        penalty_factor = 1.0 - _clamp01((volatility_penalty + drawdown_penalty) / 2.0)
        total = _clamp01(raw * penalty_factor)
        return ScoreBreakdown(
            momentum_medium=round(momentum_medium, 6),
            momentum_long=round(momentum_long, 6),
            trend_strength=round(trend_strength, 6),
            volatility_penalty=round(volatility_penalty, 6),
            drawdown_penalty=round(drawdown_penalty, 6),
            total=round(total, 6),
        )

    # --- portfolio construction ------------------------------------------

    def generate_target_portfolio(self, context: StrategyContext) -> StrategyResult:
        p = {**self.parameters, **(context.parameters or {})}
        evaluations: list[SymbolEvaluation] = []
        candidates: list[SymbolEvaluation] = []

        for symbol in context.universe:
            bars = context.bars.get(symbol, [])
            ind = compute_indicators(bars)
            reasons = self._check_eligibility(symbol, context, ind, len(bars))
            if reasons:
                evaluations.append(
                    SymbolEvaluation(
                        symbol=symbol, eligible=False,
                        exclusion_reasons=reasons, indicators=ind,
                    )
                )
                continue
            breakdown = self._score(ind)
            evaluation = SymbolEvaluation(
                symbol=symbol, eligible=True, indicators=ind,
                score=breakdown.total, score_breakdown=breakdown,
            )
            evaluations.append(evaluation)
            if breakdown.total >= float(p["min_score"]):
                candidates.append(evaluation)
            else:
                evaluation.exclusion_reasons.append(
                    f"score_below_minimum ({breakdown.total:.3f} < {p['min_score']})"
                )

        selected = sorted(candidates, key=lambda e: e.score or 0.0, reverse=True)[
            : int(p["max_positions"])
        ]

        # Inverse-volatility weighting with per-position cap.
        inv_vols: dict[str, float] = {}
        for ev in selected:
            vol = ev.indicators.realized_vol_21d
            if vol is None or vol <= 0 or not math.isfinite(vol):
                continue  # defensive; eligibility already requires vol
            inv_vols[ev.symbol] = 1.0 / max(vol, 0.02)  # floor avoids huge weights

        targets: list[TargetWeight] = []
        total_inv = sum(inv_vols.values())
        if total_inv > 0:
            cap = float(p["max_position_weight"])
            raw_weights = {s: iv / total_inv for s, iv in inv_vols.items()}
            capped = {s: min(w, cap) for s, w in raw_weights.items()}
            for ev in selected:
                if ev.symbol not in capped:
                    continue
                # Floor (not round) so the invested total can never creep
                # above 100% through rounding-up of many small weights.
                weight = math.floor(capped[ev.symbol] * 1e6) / 1e6
                if weight <= 0:
                    continue
                ind = ev.indicators
                targets.append(
                    TargetWeight(
                        symbol=ev.symbol,
                        target_weight=weight,
                        score=ev.score,
                        reasons=[
                            "Price above 200-day moving average",
                            "50-day moving average above 200-day moving average",
                            f"Momentum 63d {ind.momentum_63d:+.1%}, "
                            f"126d {ind.momentum_126d:+.1%}",
                            f"Inverse-volatility weight (vol {ind.realized_vol_21d:.1%})",
                        ],
                    )
                )

        invested = sum(t.target_weight for t in targets)
        cash_target = round(max(0.0, 1.0 - invested), 6)
        portfolio = TargetPortfolio(
            strategy_name=self.name,
            strategy_version=self.version,
            as_of=context.as_of,
            targets=targets,
            cash_target=cash_target,
        )
        return StrategyResult(portfolio=portfolio, evaluations=evaluations)
