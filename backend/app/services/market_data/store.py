"""Persistence for validated daily bars and assets."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.market_data import Asset, DailyBar
from app.schemas.market_data import AssetInfo, BarData
from app.services.market_data.quality import validate_bars

logger = get_logger("market_data.store")


async def upsert_bars(session: AsyncSession, symbol: str, bars: list[BarData]) -> int:
    """Validate and store bars for a symbol. Existing (symbol, date, source)
    rows are replaced. Returns the number of stored bars."""
    result = validate_bars(symbol, bars)
    for bar, reason in result.rejected:
        log_event(
            logger, "bar_rejected", f"rejected bar for {symbol}",
            symbol=symbol, bar_date=str(bar.bar_date), reason=reason,
        )
    if not result.clean_bars:
        return 0

    dates = [b.bar_date for b in result.clean_bars]
    sources = {b.source for b in result.clean_bars}
    await session.execute(
        delete(DailyBar).where(
            DailyBar.symbol == symbol,
            DailyBar.bar_date.in_(dates),
            DailyBar.source.in_(sources),
        )
    )
    for flag in result.flags:
        log_event(logger, "bar_flagged", flag, symbol=symbol)
    series_flags = result.flags
    session.add_all(
        DailyBar(
            symbol=b.symbol,
            bar_date=b.bar_date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            adjusted_close=b.adjusted_close,
            volume=b.volume,
            source=b.source,
            quality_flags=[f for f in series_flags if str(b.bar_date) in f],
        )
        for b in result.clean_bars
    )
    await session.flush()
    return len(result.clean_bars)


async def load_bars(
    session: AsyncSession, symbol: str, start: date, end: date
) -> list[BarData]:
    rows = (
        await session.execute(
            select(DailyBar)
            .where(DailyBar.symbol == symbol, DailyBar.bar_date.between(start, end))
            .order_by(DailyBar.bar_date)
        )
    ).scalars().all()
    return [
        BarData(
            symbol=r.symbol,
            bar_date=r.bar_date,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            adjusted_close=r.adjusted_close,
            volume=r.volume,
            source=r.source,
        )
        for r in rows
    ]


async def upsert_asset(session: AsyncSession, info: AssetInfo) -> Asset:
    existing = (
        await session.execute(select(Asset).where(Asset.symbol == info.symbol))
    ).scalar_one_or_none()
    if existing is None:
        existing = Asset(symbol=info.symbol)
        session.add(existing)
    existing.name = info.name
    existing.exchange = info.exchange
    existing.asset_class = info.asset_class
    existing.tradable = info.tradable
    existing.fractionable = info.fractionable
    existing.status = info.status
    await session.flush()
    return existing
