"""Risk-engine domain objects: limits, trade intents, verdicts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RiskLimits(BaseModel):
    """Configurable limits with conservative defaults.

    These starter values are deliberately cautious; nothing here is claimed
    to be optimal.
    """

    # Account rules
    allow_leverage: bool = False          # hard False; kept for explicit auditing
    allow_shorting: bool = False          # hard False
    min_cash_reserve_pct: float = 0.05
    max_invested_pct: float = 0.95
    max_daily_turnover_pct: float = 0.35
    max_open_positions: int = 10
    max_new_capital_per_rebalance_pct: float = 0.50

    # Position rules
    max_position_pct: float = 0.15
    max_position_notional: float = 25_000.0
    min_order_notional: float = 100.0
    max_order_notional: float = 10_000.0
    max_pct_of_avg_daily_volume: float = 0.01
    min_price: float = 5.0

    # Loss / drawdown rules
    daily_loss_limit_pct: float = 0.03
    strategy_drawdown_limit_pct: float = 0.15
    position_stop_loss_alert_pct: float = 0.15
    portfolio_volatility_limit: float = 0.35   # annualized
    max_consecutive_errors: int = 3
    max_consecutive_rejected_orders: int = 3

    # Operational
    stale_data_max_age_minutes: int = 30
    max_clock_skew_seconds: int = 120
    auto_liquidate_on_limit: bool = False  # never liquidate unless user opts in


class TradeIntent(BaseModel):
    """A proposed trade entering risk review (pre-approval)."""

    symbol: str
    side: str  # "buy" | "sell"
    quantity: float = Field(gt=0)
    notional: float = Field(gt=0)
    reference_price: float = Field(gt=0)
    current_weight: float = 0.0
    target_weight: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class AccountState(BaseModel):
    """Deterministic snapshot of everything the risk engine needs."""

    equity: float
    cash: float
    buying_power: float
    positions: dict[str, float] = Field(default_factory=dict)        # symbol -> qty
    position_values: dict[str, float] = Field(default_factory=dict)  # symbol -> $
    open_orders: int = 0
    daily_pl_pct: float = 0.0
    drawdown_pct: float = 0.0
    portfolio_volatility: float | None = None
    consecutive_errors: int = 0
    consecutive_rejected_orders: int = 0


class MarketContext(BaseModel):
    """Per-symbol facts the risk engine checks against."""

    prices: dict[str, float] = Field(default_factory=dict)
    price_timestamps: dict[str, datetime] = Field(default_factory=dict)
    tradable: dict[str, bool] = Field(default_factory=dict)
    avg_daily_volumes: dict[str, float] = Field(default_factory=dict)  # shares/day
    approved_universe: list[str] = Field(default_factory=list)
    now: datetime


class RiskAction(StrEnum):
    APPROVE = "approve"
    RESIZE = "resize"
    REJECT = "reject"
    FREEZE = "freeze"


class RuleCheck(BaseModel):
    rule_name: str
    passed: bool
    actual_value: float | None = None
    limit_value: float | None = None
    message: str = ""


class RiskVerdict(BaseModel):
    """Outcome of risk review for one trade intent."""

    action: RiskAction
    intent: TradeIntent
    approved_quantity: float = 0.0
    approved_notional: float = 0.0
    rule_name: str = ""            # rule that rejected/resized/froze
    actual_value: float | None = None
    limit_value: float | None = None
    checks: list[RuleCheck] = Field(default_factory=list)
    message: str = ""
