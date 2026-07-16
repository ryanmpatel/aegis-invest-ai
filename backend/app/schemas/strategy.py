"""Strategy interface domain objects.

A strategy consumes a StrategyContext (validated historical data + account
state) and returns a TargetPortfolio (weights, not orders). The same objects
are used in backtests, previews, and paper trading.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.market_data import BarData


class IndicatorSet(BaseModel):
    """Computed per-symbol indicators, persisted for explainability."""

    latest_price: float | None = None
    latest_price_date: date | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    realized_vol_21d: float | None = None      # annualized
    momentum_63d: float | None = None          # fractional return
    momentum_126d: float | None = None
    avg_dollar_volume_20d: float | None = None
    distance_from_52w_high: float | None = None  # <= 0, fraction below high
    max_drawdown_63d: float | None = None        # <= 0

    def as_dict(self) -> dict[str, float | str | None]:
        data = self.model_dump()
        if data.get("latest_price_date") is not None:
            data["latest_price_date"] = data["latest_price_date"].isoformat()
        return data


class ScoreBreakdown(BaseModel):
    momentum_medium: float = 0.0
    momentum_long: float = 0.0
    trend_strength: float = 0.0
    volatility_penalty: float = 0.0
    drawdown_penalty: float = 0.0
    total: float = 0.0


class TargetWeight(BaseModel):
    symbol: str
    target_weight: float = Field(ge=0.0, le=1.0)
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class TargetPortfolio(BaseModel):
    strategy_name: str
    strategy_version: str
    as_of: datetime
    targets: list[TargetWeight] = Field(default_factory=list)
    cash_target: float = Field(ge=0.0, le=1.0, default=0.0)

    @model_validator(mode="after")
    def _weights_must_not_exceed_one(self) -> TargetPortfolio:
        total = sum(t.target_weight for t in self.targets) + self.cash_target
        if total > 1.0 + 1e-6:
            raise ValueError(f"Target weights plus cash exceed 100% (got {total:.4f}).")
        return self


class StrategyContext(BaseModel):
    """Everything a strategy is allowed to see. Notably absent: any broker
    client, API credentials, or the ability to place orders."""

    as_of: datetime
    universe: list[str]
    bars: dict[str, list[BarData]]              # per-symbol history, ascending by date
    tradable: dict[str, bool] = Field(default_factory=dict)
    ai_risk_flags: dict[str, str] = Field(default_factory=dict)  # symbol -> risk_level
    parameters: dict[str, float | int | str | bool] = Field(default_factory=dict)


class SymbolEvaluation(BaseModel):
    """Full per-symbol evaluation output, persisted as a Signal row."""

    symbol: str
    eligible: bool
    exclusion_reasons: list[str] = Field(default_factory=list)
    indicators: IndicatorSet = Field(default_factory=IndicatorSet)
    score: float | None = None
    score_breakdown: ScoreBreakdown | None = None


class StrategyResult(BaseModel):
    portfolio: TargetPortfolio
    evaluations: list[SymbolEvaluation] = Field(default_factory=list)
