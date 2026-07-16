"""Market-data provider interface."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.schemas.market_data import (
    AssetInfo,
    BarData,
    CalendarDay,
    NewsItem,
    QuoteData,
    TradeData,
)


@runtime_checkable
class MarketDataProvider(Protocol):
    """All methods are read-only; a data provider can never place orders."""

    name: str

    async def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[BarData]]: ...

    async def get_latest_trade(self, symbol: str) -> TradeData | None: ...

    async def get_latest_quote(self, symbol: str) -> QuoteData | None: ...

    async def get_market_calendar(self, start: date, end: date) -> list[CalendarDay]: ...

    async def get_asset(self, symbol: str) -> AssetInfo | None: ...

    async def get_news(
        self, symbols: list[str], start: date | None = None, end: date | None = None,
        limit: int = 50,
    ) -> list[NewsItem]: ...
