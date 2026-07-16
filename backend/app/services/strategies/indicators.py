"""Technical indicators computed from daily bars.

All functions take bars in ascending date order and use adjusted close when
available. They return ``None`` when there is insufficient data — callers must
treat ``None`` as "symbol not eligible", never as zero.
"""

from __future__ import annotations

import itertools
import math

from app.schemas.market_data import BarData
from app.schemas.strategy import IndicatorSet

TRADING_DAYS_PER_YEAR = 252


def _closes(bars: list[BarData]) -> list[float]:
    return [b.adjusted_close if b.adjusted_close is not None else b.close for b in bars]


def sma(bars: list[BarData], window: int) -> float | None:
    closes = _closes(bars)
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def realized_volatility(bars: list[BarData], window: int = 21) -> float | None:
    """Annualized standard deviation of daily log returns."""
    closes = _closes(bars)
    if len(closes) < window + 1:
        return None
    tail = closes[-(window + 1):]
    returns = [math.log(b / a) for a, b in itertools.pairwise(tail) if a > 0]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


def momentum(bars: list[BarData], window: int) -> float | None:
    """Fractional return over the last ``window`` trading days."""
    closes = _closes(bars)
    if len(closes) < window + 1:
        return None
    past = closes[-(window + 1)]
    if past <= 0:
        return None
    return closes[-1] / past - 1.0


def avg_dollar_volume(bars: list[BarData], window: int = 20) -> float | None:
    if len(bars) < window:
        return None
    tail = bars[-window:]
    return sum(b.close * b.volume for b in tail) / window


def avg_share_volume(bars: list[BarData], window: int = 20) -> float | None:
    if len(bars) < window:
        return None
    return sum(b.volume for b in bars[-window:]) / window


def distance_from_52w_high(bars: list[BarData]) -> float | None:
    """Fraction below the trailing-252-day high (<= 0)."""
    closes = _closes(bars)
    if len(closes) < 20:
        return None
    window = closes[-TRADING_DAYS_PER_YEAR:]
    high = max(window)
    if high <= 0:
        return None
    return closes[-1] / high - 1.0


def max_drawdown(bars: list[BarData], window: int = 63) -> float | None:
    """Worst peak-to-trough decline within the window (<= 0)."""
    closes = _closes(bars)
    if len(closes) < 2:
        return None
    tail = closes[-window:]
    peak = tail[0]
    worst = 0.0
    for price in tail:
        peak = max(peak, price)
        if peak > 0:
            worst = min(worst, price / peak - 1.0)
    return worst


def compute_indicators(bars: list[BarData]) -> IndicatorSet:
    latest = bars[-1] if bars else None
    return IndicatorSet(
        latest_price=(_closes(bars)[-1] if bars else None),
        latest_price_date=(latest.bar_date if latest else None),
        sma_20=sma(bars, 20),
        sma_50=sma(bars, 50),
        sma_200=sma(bars, 200),
        realized_vol_21d=realized_volatility(bars, 21),
        momentum_63d=momentum(bars, 63),
        momentum_126d=momentum(bars, 126),
        avg_dollar_volume_20d=avg_dollar_volume(bars, 20),
        distance_from_52w_high=distance_from_52w_high(bars),
        max_drawdown_63d=max_drawdown(bars, 63),
    )
