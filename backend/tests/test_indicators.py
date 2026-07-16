"""Unit tests for every indicator."""

from __future__ import annotations

import math
from datetime import date

import pytest

from app.schemas.market_data import BarData
from app.services.strategies import indicators as ind
from tests.helpers import make_bars


def flat_bars(n: int, price: float = 100.0, volume: float = 1_000_000) -> list[BarData]:
    return make_bars("TEST", n, start_price=price, daily_return=0.0, volume=volume)


class TestSMA:
    def test_flat_series(self):
        bars = flat_bars(60)
        assert ind.sma(bars, 20) == pytest.approx(100.0, rel=1e-3)

    def test_insufficient_data_returns_none(self):
        assert ind.sma(flat_bars(10), 20) is None

    def test_uses_last_window_only(self):
        bars = make_bars("TEST", 100, daily_return=0.01)
        closes = [b.close for b in bars]
        assert ind.sma(bars, 20) == pytest.approx(sum(closes[-20:]) / 20)


class TestRealizedVolatility:
    def test_zero_vol_for_constant_returns(self):
        bars = make_bars("TEST", 50, daily_return=0.001)
        vol = ind.realized_volatility(bars, 21)
        assert vol == pytest.approx(0.0, abs=1e-4)  # rounding noise only

    def test_positive_for_noisy_series(self):
        bars = make_bars("TEST", 50, daily_return=0.0, volatility=0.02)
        vol = ind.realized_volatility(bars, 21)
        assert vol is not None and vol > 0.1

    def test_insufficient_data(self):
        assert ind.realized_volatility(flat_bars(10), 21) is None


class TestMomentum:
    def test_positive_momentum(self):
        bars = make_bars("TEST", 130, daily_return=0.001)
        m = ind.momentum(bars, 63)
        assert m == pytest.approx(math.exp(0.001 * 63) - 1, rel=1e-4)

    def test_negative_momentum(self):
        bars = make_bars("TEST", 130, daily_return=-0.002)
        m = ind.momentum(bars, 63)
        assert m is not None and m < 0

    def test_insufficient_data(self):
        assert ind.momentum(flat_bars(30), 63) is None


class TestVolumeAndHighs:
    def test_avg_dollar_volume(self):
        bars = flat_bars(30, price=100.0, volume=1_000_000)
        adv = ind.avg_dollar_volume(bars, 20)
        assert adv == pytest.approx(100.0 * 1_000_000, rel=0.01)

    def test_avg_share_volume(self):
        bars = flat_bars(30, volume=500_000)
        assert ind.avg_share_volume(bars, 20) == pytest.approx(500_000)

    def test_distance_from_52w_high_at_high(self):
        bars = make_bars("TEST", 260, daily_return=0.001)
        dist = ind.distance_from_52w_high(bars)
        assert dist is not None and -0.01 <= dist <= 0.0

    def test_distance_from_52w_high_below(self):
        up = make_bars("TEST", 200, daily_return=0.002, end=date(2026, 3, 31))
        down = make_bars(
            "TEST", 60, start_price=up[-1].close, daily_return=-0.003,
            end=date(2026, 6, 30),
        )
        dist = ind.distance_from_52w_high(up + down)
        assert dist is not None and dist < -0.05


class TestMaxDrawdown:
    def test_monotonic_up_has_no_drawdown(self):
        bars = make_bars("TEST", 80, daily_return=0.002)
        dd = ind.max_drawdown(bars, 63)
        assert dd == pytest.approx(0.0, abs=1e-6)

    def test_known_drawdown(self):
        up = make_bars("TEST", 40, start_price=100, daily_return=0.0,
                       end=date(2026, 5, 1))
        crash = make_bars("TEST", 23, start_price=100, daily_return=-0.01,
                          end=date(2026, 6, 1))
        dd = ind.max_drawdown(up + crash, 63)
        assert dd is not None
        assert dd == pytest.approx(math.exp(-0.01 * 23) - 1, rel=0.05)


class TestComputeIndicators:
    def test_full_set_present_with_enough_history(self):
        bars = make_bars("TEST", 260, daily_return=0.0005, volatility=0.01)
        result = ind.compute_indicators(bars)
        assert result.latest_price is not None
        assert result.sma_20 is not None
        assert result.sma_50 is not None
        assert result.sma_200 is not None
        assert result.realized_vol_21d is not None
        assert result.momentum_63d is not None
        assert result.momentum_126d is not None
        assert result.avg_dollar_volume_20d is not None
        assert result.distance_from_52w_high is not None
        assert result.max_drawdown_63d is not None

    def test_empty_bars(self):
        result = ind.compute_indicators([])
        assert result.latest_price is None
        assert result.sma_200 is None
