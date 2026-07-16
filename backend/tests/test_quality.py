"""Data-quality validation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.market_data.quality import (
    check_gaps,
    is_price_stale,
    validate_bars,
)
from tests.helpers import make_bars


class TestValidateBars:
    def test_clean_series_passes(self):
        bars = make_bars("SPY", 50)
        result = validate_bars("SPY", bars)
        assert result.ok
        assert len(result.clean_bars) == 50

    def test_duplicate_bar_rejected(self):
        bars = make_bars("SPY", 10)
        result = validate_bars("SPY", [*bars, bars[-1]])
        assert any(reason == "duplicate_bar" for _, reason in result.rejected)
        assert len(result.clean_bars) == 10

    def test_future_dated_rejected(self):
        bars = make_bars("SPY", 5)
        future = bars[-1].model_copy(
            update={"bar_date": datetime.now(UTC).date() + timedelta(days=10)}
        )
        result = validate_bars("SPY", [*bars[:-1], future])
        assert any(reason == "future_dated" for _, reason in result.rejected)

    def test_symbol_mismatch_rejected(self):
        bars = make_bars("SPY", 5)
        wrong = bars[0].model_copy(update={"symbol": "QQQ"})
        result = validate_bars("SPY", [wrong, *bars[1:]])
        assert any(reason == "symbol_mismatch" for _, reason in result.rejected)

    def test_extreme_move_flagged(self):
        bars = make_bars("SPY", 10)
        spike = bars[-1].model_copy(update={"close": bars[-1].close * 2})
        result = validate_bars("SPY", [*bars[:-1], spike])
        assert result.flags  # extreme move flagged, not rejected

    def test_zero_volume_rejected(self):
        bars = make_bars("SPY", 5)
        object.__setattr__(bars[2], "volume", 0.0)
        result = validate_bars("SPY", bars)
        assert any(reason == "non_positive_volume" for _, reason in result.rejected)


class TestGapsAndStaleness:
    def test_gap_detection(self):
        early = make_bars("SPY", 5, end=datetime(2026, 1, 30, tzinfo=UTC).date())
        late = make_bars("SPY", 5, end=datetime(2026, 3, 31, tzinfo=UTC).date())
        assert check_gaps(early + late)

    def test_no_gap_for_contiguous_days(self):
        assert check_gaps(make_bars("SPY", 30)) == []

    def test_stale_price_when_market_open(self):
        old = datetime.now(UTC) - timedelta(hours=2)
        assert is_price_stale(old, max_age_minutes=30, market_open=True)

    def test_fresh_price_ok(self):
        recent = datetime.now(UTC) - timedelta(minutes=5)
        assert not is_price_stale(recent, max_age_minutes=30, market_open=True)

    def test_weekend_tolerance_when_closed(self):
        two_days = datetime.now(UTC) - timedelta(days=2)
        assert not is_price_stale(two_days, market_open=False)

    def test_future_price_is_stale(self):
        future = datetime.now(UTC) + timedelta(hours=1)
        assert is_price_stale(future)
