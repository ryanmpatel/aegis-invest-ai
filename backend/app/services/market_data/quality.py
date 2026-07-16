"""Data-quality validation for market data.

Rejects or flags: duplicate bars, missing timestamps, negative prices,
zero/negative volume, extreme unexplained moves, stale prices, future-dated
prices, and unsupported symbols.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.schemas.market_data import BarData

MAX_DAILY_MOVE = 0.35  # |return| above this is flagged as extreme


@dataclass
class ValidationResult:
    clean_bars: list[BarData] = field(default_factory=list)
    rejected: list[tuple[BarData, str]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected and not self.flags


def validate_bars(symbol: str, bars: list[BarData]) -> ValidationResult:
    """Validate one symbol's daily-bar series (ascending order enforced)."""
    result = ValidationResult()
    today = datetime.now(UTC).date()
    seen_dates: set = set()
    ordered = sorted(bars, key=lambda b: b.bar_date)
    prev_close: float | None = None

    for bar in ordered:
        if bar.symbol != symbol:
            result.rejected.append((bar, "symbol_mismatch"))
            continue
        if bar.bar_date in seen_dates:
            result.rejected.append((bar, "duplicate_bar"))
            continue
        if bar.bar_date > today:
            result.rejected.append((bar, "future_dated"))
            continue
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            result.rejected.append((bar, "non_positive_price"))
            continue
        if any(
            not math.isfinite(v) for v in (bar.open, bar.high, bar.low, bar.close, bar.volume)
        ):
            result.rejected.append((bar, "non_finite_value"))
            continue
        if bar.volume <= 0:
            result.rejected.append((bar, "non_positive_volume"))
            continue
        if bar.high < bar.low:
            result.rejected.append((bar, "high_below_low"))
            continue
        if prev_close is not None and prev_close > 0:
            move = abs(bar.close / prev_close - 1.0)
            if move > MAX_DAILY_MOVE:
                result.flags.append(
                    f"{symbol} {bar.bar_date.isoformat()}: extreme move {move:.1%}"
                )
        seen_dates.add(bar.bar_date)
        prev_close = bar.close
        result.clean_bars.append(bar)

    return result


def check_gaps(bars: list[BarData], max_gap_days: int = 7) -> list[str]:
    """Flag suspicious gaps between consecutive bars (holidays span < a week)."""
    flags = []
    ordered = sorted(bars, key=lambda b: b.bar_date)
    for prev, cur in itertools.pairwise(ordered):
        gap = (cur.bar_date - prev.bar_date).days
        if gap > max_gap_days:
            flags.append(
                f"{cur.symbol}: {gap}-day gap between "
                f"{prev.bar_date.isoformat()} and {cur.bar_date.isoformat()}"
            )
    return flags


def is_price_stale(
    price_timestamp: datetime, now: datetime | None = None, max_age_minutes: int = 30,
    market_open: bool = True,
) -> bool:
    """A current price is stale if it is older than the allowed age while the
    market is open, or older than ~3 days regardless (covers weekends)."""
    now = now or datetime.now(UTC)
    if price_timestamp.tzinfo is None:
        price_timestamp = price_timestamp.replace(tzinfo=UTC)
    age = now - price_timestamp
    if age < timedelta(0):
        return True  # future-dated price is never acceptable
    if market_open:
        return age > timedelta(minutes=max_age_minutes)
    return age > timedelta(days=3)


def has_sufficient_history(bars: list[BarData], min_bars: int) -> bool:
    return len(bars) >= min_bars
