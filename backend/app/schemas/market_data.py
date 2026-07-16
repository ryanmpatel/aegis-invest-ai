"""Market-data domain objects."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class BarData(BaseModel):
    symbol: str
    bar_date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    adjusted_close: float | None = None
    volume: float = Field(ge=0)
    source: str = "unknown"


class QuoteData(BaseModel):
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float = 0
    ask_size: float = 0
    timestamp: datetime


class TradeData(BaseModel):
    symbol: str
    price: float
    size: float = 0
    timestamp: datetime


class AssetInfo(BaseModel):
    symbol: str
    name: str = ""
    exchange: str = ""
    asset_class: str = "us_equity"
    tradable: bool = False
    fractionable: bool = False
    status: str = "active"


class CalendarDay(BaseModel):
    calendar_date: date
    is_open: bool = True
    session_open: str = "09:30"
    session_close: str = "16:00"


class NewsItem(BaseModel):
    external_id: str
    source: str = "unknown"
    symbols: list[str] = Field(default_factory=list)
    headline: str = ""
    summary: str = ""
    content: str = ""
    url: str = ""
    published_at: datetime | None = None
