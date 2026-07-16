"""Test data builders."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from app.schemas.market_data import BarData


def make_bars(
    symbol: str,
    n: int = 250,
    *,
    start_price: float = 100.0,
    daily_return: float = 0.001,
    volatility: float = 0.0,
    volume: float = 2_000_000,
    end: date | None = None,
    seed: int = 42,
) -> list[BarData]:
    """Deterministic bar series ending today (or `end`)."""
    rng = random.Random(seed)
    end = end or date.today()
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()

    bars: list[BarData] = []
    price = start_price
    for day in days:
        ret = daily_return + (rng.gauss(0, volatility) if volatility else 0.0)
        new_price = max(0.01, price * math.exp(ret))
        bars.append(
            BarData(
                symbol=symbol,
                bar_date=day,
                open=round(price, 4),
                high=round(max(price, new_price) * 1.005, 4),
                low=round(min(price, new_price) * 0.995, 4),
                close=round(new_price, 4),
                adjusted_close=round(new_price, 4),
                volume=volume,
                source="test",
            )
        )
        price = new_price
    return bars
