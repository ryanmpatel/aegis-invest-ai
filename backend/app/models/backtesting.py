"""Backtesting models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    strategy_name: Mapped[str] = mapped_column(String(128))
    strategy_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    # pending | running | completed | failed
    error: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # start/end dates, capital, costs, spread, slippage, benchmark, universe,
    # rebalance frequency, data-split labels (train/validation/test)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_backtest_trades_run", "backtest_run_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    backtest_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtest_runs.id"))
    trade_date: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_cost: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")


class BacktestDailyResult(Base):
    __tablename__ = "backtest_daily_results"
    __table_args__ = (Index("ix_backtest_daily_run_date", "backtest_run_id", "result_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    backtest_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtest_runs.id"))
    result_date: Mapped[date] = mapped_column(Date)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    invested_value: Mapped[float] = mapped_column(Float)
    daily_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark_equity: Mapped[float | None] = mapped_column(Float, nullable=True)


class BacktestPosition(Base):
    __tablename__ = "backtest_positions"
    __table_args__ = (Index("ix_backtest_positions_run_date", "backtest_run_id", "as_of_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    backtest_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtest_runs.id"))
    as_of_date: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    market_value: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
