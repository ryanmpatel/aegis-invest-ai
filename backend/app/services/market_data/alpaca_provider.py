"""Alpaca market-data provider (read-only).

``alpaca-py`` is imported lazily so mock-only deployments need not install it.
This module never places orders — it only reads data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.config import Settings
from app.logging import get_logger
from app.schemas.market_data import (
    AssetInfo,
    BarData,
    CalendarDay,
    NewsItem,
    QuoteData,
    TradeData,
)
from app.utils.retry import retry_async

logger = get_logger("market_data.alpaca")


class AlpacaMarketDataProvider:
    name = "alpaca"

    def __init__(self, settings: Settings) -> None:
        api_key = settings.alpaca_paper_api_key.get_secret_value()
        api_secret = settings.alpaca_paper_api_secret.get_secret_value()
        if not api_key or not api_secret:
            raise RuntimeError(
                "Alpaca market data requires ALPACA_PAPER_API_KEY and "
                "ALPACA_PAPER_API_SECRET."
            )
        try:
            from alpaca.data.historical import (
                NewsClient,
                StockHistoricalDataClient,
            )
            from alpaca.trading.client import TradingClient
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "alpaca-py is not installed. Install with: pip install '.[alpaca]'"
            ) from exc

        self._data = StockHistoricalDataClient(api_key, api_secret)
        self._news = NewsClient(api_key, api_secret)
        # TradingClient used strictly for read-only metadata (assets, calendar,
        # clock). paper=True is hard-coded; this class exposes no order methods.
        self._trading = TradingClient(api_key, api_secret, paper=True)

    async def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[BarData]]:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            end=datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            adjustment="all",
        )
        response = await retry_async(lambda: self._data.get_stock_bars(request))
        out: dict[str, list[BarData]] = {s: [] for s in symbols}
        data: dict[str, Any] = getattr(response, "data", {}) or {}
        for symbol, bars in data.items():
            for bar in bars:
                out.setdefault(symbol, []).append(
                    BarData(
                        symbol=symbol,
                        bar_date=bar.timestamp.date(),
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        adjusted_close=float(bar.close),  # adjustment="all" pre-adjusts
                        volume=float(bar.volume),
                        source=self.name,
                    )
                )
        return out

    async def get_latest_trade(self, symbol: str) -> TradeData | None:
        from alpaca.data.requests import StockLatestTradeRequest

        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        response = await retry_async(lambda: self._data.get_stock_latest_trade(request))
        trade = response.get(symbol)
        if trade is None:
            return None
        return TradeData(
            symbol=symbol,
            price=float(trade.price),
            size=float(trade.size or 0),
            timestamp=trade.timestamp,
        )

    async def get_latest_quote(self, symbol: str) -> QuoteData | None:
        from alpaca.data.requests import StockLatestQuoteRequest

        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        response = await retry_async(lambda: self._data.get_stock_latest_quote(request))
        quote = response.get(symbol)
        if quote is None:
            return None
        return QuoteData(
            symbol=symbol,
            bid_price=float(quote.bid_price),
            ask_price=float(quote.ask_price),
            bid_size=float(quote.bid_size or 0),
            ask_size=float(quote.ask_size or 0),
            timestamp=quote.timestamp,
        )

    async def get_market_calendar(self, start: date, end: date) -> list[CalendarDay]:
        from alpaca.trading.requests import GetCalendarRequest

        request = GetCalendarRequest(start=start, end=end)
        days = await retry_async(lambda: self._trading.get_calendar(request))
        return [
            CalendarDay(
                calendar_date=d.date,
                is_open=True,
                session_open=d.open.strftime("%H:%M"),
                session_close=d.close.strftime("%H:%M"),
            )
            for d in days
        ]

    async def get_asset(self, symbol: str) -> AssetInfo | None:
        try:
            asset = await retry_async(lambda: self._trading.get_asset(symbol))
        except Exception:
            logger.warning("asset lookup failed", extra={"symbol": symbol})
            return None
        return AssetInfo(
            symbol=asset.symbol,
            name=asset.name or "",
            exchange=str(asset.exchange or ""),
            asset_class=str(asset.asset_class or "us_equity"),
            tradable=bool(asset.tradable),
            fractionable=bool(asset.fractionable),
            status=str(asset.status or "active"),
        )

    async def get_news(
        self,
        symbols: list[str],
        start: date | None = None,
        end: date | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        from alpaca.data.requests import NewsRequest

        request = NewsRequest(
            symbols=",".join(symbols),
            start=datetime.combine(start, datetime.min.time(), tzinfo=UTC) if start else None,
            end=datetime.combine(end, datetime.max.time(), tzinfo=UTC) if end else None,
            limit=limit,
        )
        response = await retry_async(lambda: self._news.get_news(request))
        items: list[NewsItem] = []
        for article in getattr(response, "news", []) or []:
            items.append(
                NewsItem(
                    external_id=str(article.id),
                    source=self.name,
                    symbols=list(article.symbols or []),
                    headline=article.headline or "",
                    summary=article.summary or "",
                    content=article.content or "",
                    url=str(article.url or ""),
                    published_at=article.created_at,
                )
            )
        return items
