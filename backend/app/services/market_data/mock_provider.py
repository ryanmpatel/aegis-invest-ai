"""Deterministic synthetic market data for development and tests.

Prices follow a seeded geometric random walk with per-symbol drift/volatility,
so runs are reproducible and no external API is needed.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import UTC, date, datetime, time, timedelta

from app.schemas.market_data import (
    AssetInfo,
    BarData,
    CalendarDay,
    NewsItem,
    QuoteData,
    TradeData,
)

_DEFAULT_UNIVERSE: dict[str, dict[str, float | str | bool]] = {
    "SPY": {"name": "Mock S&P 500 ETF", "start": 400.0, "drift": 0.08, "vol": 0.15},
    "QQQ": {"name": "Mock Nasdaq 100 ETF", "start": 350.0, "drift": 0.10, "vol": 0.20},
    "IWM": {"name": "Mock Russell 2000 ETF", "start": 180.0, "drift": 0.05, "vol": 0.22},
    "EFA": {"name": "Mock EAFE ETF", "start": 70.0, "drift": 0.04, "vol": 0.16},
    "AGG": {"name": "Mock Aggregate Bond ETF", "start": 100.0, "drift": 0.02, "vol": 0.05},
    "GLD": {"name": "Mock Gold ETF", "start": 180.0, "drift": 0.05, "vol": 0.14},
    "VNQ": {"name": "Mock REIT ETF", "start": 85.0, "drift": 0.03, "vol": 0.20},
    "XLE": {"name": "Mock Energy ETF", "start": 80.0, "drift": 0.06, "vol": 0.25},
    "TLT": {"name": "Mock 20+ Yr Treasury ETF", "start": 95.0, "drift": 0.01, "vol": 0.12},
    "DOWN": {"name": "Mock Downtrend ETF", "start": 120.0, "drift": -0.25, "vol": 0.30},
}

_EPOCH = date(2018, 1, 2)


def _symbol_seed(symbol: str) -> int:
    return int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:4], "big")


class MockMarketDataProvider:
    name = "mock"

    def __init__(self, universe: dict[str, dict] | None = None, seed: int = 7) -> None:
        self._universe = universe or _DEFAULT_UNIVERSE
        self._seed = seed
        self._cache: dict[str, list[BarData]] = {}

    def _trading_days(self, start: date, end: date) -> list[date]:
        days = []
        d = start
        while d <= end:
            if d.weekday() < 5:  # Mon-Fri; mock ignores holidays
                days.append(d)
            d += timedelta(days=1)
        return days

    def _series_for(self, symbol: str) -> list[BarData]:
        """Full deterministic history from _EPOCH to today, cached."""
        if symbol in self._cache:
            return self._cache[symbol]
        spec = self._universe.get(symbol)
        if spec is None:
            return []
        rng = random.Random(self._seed ^ _symbol_seed(symbol))
        daily_drift = float(spec["drift"]) / 252.0
        daily_vol = float(spec["vol"]) / math.sqrt(252.0)
        price = float(spec["start"])
        bars: list[BarData] = []
        for d in self._trading_days(_EPOCH, datetime.now(UTC).date()):
            ret = rng.gauss(daily_drift, daily_vol)
            open_p = price
            close_p = max(0.01, price * math.exp(ret))
            high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, daily_vol / 2)))
            low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, daily_vol / 2)))
            volume = max(1.0, rng.gauss(5_000_000, 1_000_000))
            bars.append(
                BarData(
                    symbol=symbol,
                    bar_date=d,
                    open=round(open_p, 4),
                    high=round(high_p, 4),
                    low=round(max(0.01, low_p), 4),
                    close=round(close_p, 4),
                    adjusted_close=round(close_p, 4),
                    volume=round(volume),
                    source=self.name,
                )
            )
            price = close_p
        self._cache[symbol] = bars
        return bars

    async def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[BarData]]:
        return {
            s: [b for b in self._series_for(s) if start <= b.bar_date <= end]
            for s in symbols
        }

    async def get_latest_trade(self, symbol: str) -> TradeData | None:
        bars = self._series_for(symbol)
        if not bars:
            return None
        last = bars[-1]
        return TradeData(
            symbol=symbol,
            price=last.close,
            size=100,
            timestamp=datetime.combine(last.bar_date, time(16, 0), tzinfo=UTC),
        )

    async def get_latest_quote(self, symbol: str) -> QuoteData | None:
        trade = await self.get_latest_trade(symbol)
        if trade is None:
            return None
        spread = trade.price * 0.0005
        return QuoteData(
            symbol=symbol,
            bid_price=round(trade.price - spread, 4),
            ask_price=round(trade.price + spread, 4),
            bid_size=100,
            ask_size=100,
            timestamp=trade.timestamp,
        )

    async def get_market_calendar(self, start: date, end: date) -> list[CalendarDay]:
        return [CalendarDay(calendar_date=d) for d in self._trading_days(start, end)]

    async def get_asset(self, symbol: str) -> AssetInfo | None:
        spec = self._universe.get(symbol)
        if spec is None:
            return None
        return AssetInfo(
            symbol=symbol,
            name=str(spec["name"]),
            exchange="MOCK",
            tradable=True,
            fractionable=True,
        )

    async def get_news(
        self,
        symbols: list[str],
        start: date | None = None,
        end: date | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        """Deterministic bland mock headlines (no real events implied)."""
        items: list[NewsItem] = []
        for symbol in symbols:
            if symbol not in self._universe:
                continue
            items.append(
                NewsItem(
                    external_id=f"mock-{symbol}-1",
                    source=self.name,
                    symbols=[symbol],
                    headline=f"{symbol}: routine market commentary",
                    summary=f"Synthetic neutral news item for {symbol} used in development.",
                    content=f"This is deterministic mock news content for {symbol}. "
                    "It carries no real-world information.",
                    url="https://example.invalid/mock-news",
                    published_at=datetime.now(UTC),
                )
            )
        return items[:limit]
