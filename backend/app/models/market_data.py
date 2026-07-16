"""Market-data models: assets, daily bars, calendars, news, AI analyses."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    asset_class: Mapped[str] = mapped_column(String(32), default="us_equity")
    exchange: Mapped[str] = mapped_column(String(32), default="")
    tradable: Mapped[bool] = mapped_column(Boolean, default=False)
    fractionable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")


class DailyBar(Base):
    """Normalized daily OHLCV bar with provenance."""

    __tablename__ = "daily_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "bar_date", "source"),
        Index("ix_daily_bars_symbol_date", "symbol", "bar_date"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    bar_date: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    adjusted_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32))
    retrieved_at: Mapped[datetime] = created_at_col()
    quality_flags: Mapped[list[str]] = mapped_column(JSON, default=list)


class MarketCalendarDay(Base):
    __tablename__ = "market_calendar_days"

    id: Mapped[uuid.UUID] = uuid_pk()
    calendar_date: Mapped[date] = mapped_column(Date, unique=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    session_open: Mapped[str] = mapped_column(String(8), default="09:30")   # US/Eastern
    session_close: Mapped[str] = mapped_column(String(8), default="16:00")  # US/Eastern


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128))
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    headline: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AINewsAnalysis(Base):
    """Validated structured output from the AI analysis provider.

    Model output is never treated as verified fact; it can only reduce
    exposure, veto buys, or flag positions for review."""

    __tablename__ = "ai_news_analyses"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    analysis_timestamp: Mapped[datetime] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(32))
    sentiment: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    time_horizon: Mapped[str] = mapped_column(String(16))
    risk_level: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text, default="")
    positive_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    negative_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    uncertainties: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_name: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("news_articles.id"), nullable=True
    )
