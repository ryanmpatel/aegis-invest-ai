"""Configuration models: settings, broker connections, strategies, risk profiles,
approved universes, and scheduler configuration."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk


class UserSettings(Base):
    """Single-row (MVP) user preference store. Never holds raw credentials."""

    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    transaction_cost_assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ai_provider: Mapped[str] = mapped_column(String(32), default="mock")


class BrokerConnection(Base):
    """Broker connection metadata. API secrets live in env vars / secret store,
    never in this table — only non-sensitive metadata is persisted."""

    __tablename__ = "broker_connections"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    provider: Mapped[str] = mapped_column(String(32))  # "mock" | "alpaca_paper"
    mode: Mapped[str] = mapped_column(String(16), default="paper")  # always "paper"
    account_id_masked: Mapped[str] = mapped_column(String(64), default="")
    last_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StrategyDefinition(Base):
    __tablename__ = "strategy_definitions"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    versions: Mapped[list[StrategyVersion]] = relationship(back_populates="definition")


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("definition_id", "version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_definitions.id"))
    version: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    definition: Mapped[StrategyDefinition] = relationship(back_populates="versions")


class RiskProfile(Base):
    """A named, versioned set of risk-engine limits. Values are conservative
    starting points, not claims of optimality."""

    __tablename__ = "risk_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class ApprovedUniverse(Base):
    """The editable list of symbols the strategy may consider."""

    __tablename__ = "approved_universes"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class SchedulerConfig(Base):
    __tablename__ = "scheduler_configs"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rebalance_cron: Mapped[str] = mapped_column(String(64), default="0 15 * * MON")
    # Set false by risk freezes; requires manual reactivation.
    trading_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    frozen_reason: Mapped[str] = mapped_column(Text, default="")
