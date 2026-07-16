"""Trading models: the immutable decision trail from strategy run to fill.

Market data → indicators → signal → target portfolio → AI adjustment →
proposed trade → risk decision → order → order events → fills → positions.

These records are append-only: rows are inserted, never mutated after the
lifecycle completes (status fields advance forward only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class StrategyRun(Base):
    """One execution of a strategy (backtest step, preview, or live rebalance)."""

    __tablename__ = "strategy_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_name: Mapped[str] = mapped_column(String(128))
    strategy_version: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16))  # preview | paper | backtest
    as_of: Mapped[datetime] = mapped_column()
    status: Mapped[str] = mapped_column(String(32), default="started")
    # started | data_validated | targets_generated | risk_reviewed |
    # orders_submitted | completed | failed | frozen
    error: Mapped[str] = mapped_column(Text, default="")
    universe: Mapped[list[str]] = mapped_column(JSON, default=list)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Signal(Base):
    """Per-symbol indicator values and score breakdown for a run."""

    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_run_symbol", "strategy_run_id", "symbol"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    strategy_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_runs.id"))
    symbol: Mapped[str] = mapped_column(String(16))
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    indicators: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TargetPortfolioRecord(Base):
    __tablename__ = "target_portfolios"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    strategy_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_runs.id"))
    as_of: Mapped[datetime] = mapped_column()
    targets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cash_target: Mapped[float] = mapped_column(Float, default=0.0)
    ai_adjustments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ProposedTrade(Base):
    __tablename__ = "proposed_trades"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    strategy_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_runs.id"))
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))  # buy | sell
    quantity: Mapped[float] = mapped_column(Float)
    notional: Mapped[float] = mapped_column(Float)
    reference_price: Mapped[float] = mapped_column(Float)
    current_weight: Mapped[float] = mapped_column(Float)
    target_weight: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)


class RiskDecision(Base):
    """Outcome of the deterministic risk review for one proposed trade."""

    __tablename__ = "risk_decisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    strategy_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_runs.id"))
    proposed_trade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposed_trades.id"))
    account_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account_snapshots.id"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(16))  # approve | resize | reject | freeze
    approved_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    approved_notional: Mapped[float] = mapped_column(Float, default=0.0)
    rule_name: Mapped[str] = mapped_column(String(64), default="")
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_version: Mapped[str] = mapped_column(String(32), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_client_order_id", "client_order_id", unique=True),)

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    strategy_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_runs.id"), nullable=True
    )
    risk_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_decisions.id"), nullable=True
    )
    client_order_id: Mapped[str] = mapped_column(String(64))
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16), default="market")
    time_in_force: Mapped[str] = mapped_column(String(8), default="day")
    quantity: Mapped[float] = mapped_column(Float)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    filled_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="new", index=True)
    # new | submitted | partially_filled | filled | canceled | rejected |
    # expired | unknown
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class OrderEvent(Base):
    """Append-only order lifecycle log."""

    __tablename__ = "order_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    filled_at: Mapped[datetime] = mapped_column()


class PositionRecord(Base):
    """Point-in-time local view of a position (refreshed on reconcile)."""

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_entry_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pl: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime] = mapped_column()
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    buying_power: Mapped[float] = mapped_column(Float)
    long_market_value: Mapped[float] = mapped_column(Float, default=0.0)
    positions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(32), default="broker")


class ReconciliationReport(Base):
    __tablename__ = "reconciliation_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    discrepancies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class RiskEvent(Base):
    """Account-level or operational risk occurrences (limits hit, freezes)."""

    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[str] = mapped_column(String(16))  # info | warning | critical
    rule_name: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


class KillSwitchEvent(Base):
    """Append-only kill-switch history; the latest row is the current state."""

    __tablename__ = "kill_switch_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    active: Mapped[bool] = mapped_column(Boolean)
    actor: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
