"""Backtesting-engine tests: invariants, look-ahead protection, costs."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.backtesting.engine import BacktestConfig, BacktestEngine
from app.services.strategies.weekly_multi_factor import WeeklyMultiFactorTrendStrategy
from tests.helpers import make_bars

END = date(2026, 6, 30)
START = date(2026, 1, 5)


def build_engine(bars_map, **config_overrides) -> BacktestEngine:
    config = BacktestConfig(
        start=START,
        end=END,
        starting_capital=100_000.0,
        universe=[s for s in bars_map if s != "SPY"] or list(bars_map),
        benchmark_symbol="SPY" if "SPY" in bars_map else None,
        **config_overrides,
    )
    return BacktestEngine(WeeklyMultiFactorTrendStrategy(), bars_map, config)


def trending_universe(n_symbols: int = 4) -> dict:
    bars_map = {
        f"S{i:02d}": make_bars(
            f"S{i:02d}", 500, daily_return=0.0006 + i * 0.0001,
            volatility=0.01, end=END, seed=i,
        )
        for i in range(n_symbols)
    }
    bars_map["SPY"] = make_bars("SPY", 500, daily_return=0.0004,
                                volatility=0.008, end=END, seed=99)
    return bars_map


class TestInvariants:
    def test_cash_never_negative(self):
        output = build_engine(trending_universe()).run()
        assert output.daily, "backtest produced no daily rows"
        for row in output.daily:
            assert row.cash >= -1e-6, f"negative cash on {row.result_date}"

    def test_no_short_positions_ever(self):
        output = build_engine(trending_universe()).run()
        for day, positions in output.positions_by_date.items():
            for symbol, qty in positions.items():
                assert qty >= -1e-9, f"short {symbol} on {day}"

    def test_equity_is_cash_plus_invested(self):
        output = build_engine(trending_universe()).run()
        for row in output.daily:
            assert row.equity == pytest.approx(row.cash + row.invested_value, abs=0.05)

    def test_trades_execute_and_are_recorded(self):
        output = build_engine(trending_universe()).run()
        assert output.trades, "expected at least one trade"
        for trade in output.trades:
            assert trade.quantity > 0
            assert trade.price > 0


class TestNoLookAhead:
    def test_future_crash_does_not_change_past_decisions(self):
        """Truncating the future must not alter decisions made before the cut."""
        bars_full = trending_universe(3)
        cut = END - timedelta(days=60)
        bars_truncated = {
            s: [b for b in series if b.bar_date <= cut]
            for s, series in bars_full.items()
        }
        config_kwargs = dict(rebalance_frequency="weekly")
        full = build_engine(bars_full, **config_kwargs)
        full_out = full.run()
        truncated = BacktestEngine(
            WeeklyMultiFactorTrendStrategy(),
            bars_truncated,
            BacktestConfig(
                start=START, end=cut, starting_capital=100_000.0,
                universe=[s for s in bars_truncated if s != "SPY"],
                benchmark_symbol="SPY",
            ),
        )
        trunc_out = truncated.run()
        # Compare equity curves on the shared date range (before the cut).
        full_by_date = {r.result_date: r.equity for r in full_out.daily}
        for row in trunc_out.daily:
            if row.result_date <= cut - timedelta(days=7):
                assert full_by_date.get(row.result_date) == pytest.approx(
                    row.equity, rel=1e-9
                ), f"look-ahead detected at {row.result_date}"


class TestCostsAndBenchmark:
    def test_costs_reduce_returns(self):
        cheap = build_engine(trending_universe(), commission_per_trade=0.0,
                             spread_bps=0.0, slippage_bps=0.0).run()
        pricey = build_engine(trending_universe(), commission_per_trade=5.0,
                              spread_bps=10.0, slippage_bps=25.0).run()
        assert pricey.daily[-1].equity < cheap.daily[-1].equity

    def test_benchmark_curve_present(self):
        output = build_engine(trending_universe()).run()
        assert any(r.benchmark_equity is not None for r in output.daily)

    def test_missing_benchmark_disables_comparison(self):
        bars_map = trending_universe()
        bars_map.pop("SPY")
        engine = BacktestEngine(
            WeeklyMultiFactorTrendStrategy(), bars_map,
            BacktestConfig(start=START, end=END, universe=list(bars_map),
                           benchmark_symbol="SPY"),
        )
        output = engine.run()
        assert all(r.benchmark_equity is None for r in output.daily)
        assert any("Benchmark" in w for w in output.warnings)


class TestDelisting:
    def test_symbol_whose_data_ends_is_liquidated(self):
        bars_map = trending_universe(3)
        # Chop one symbol's data mid-backtest to simulate delisting.
        cut = END - timedelta(days=90)
        bars_map["S00"] = [b for b in bars_map["S00"] if b.bar_date <= cut]
        output = build_engine(bars_map).run()
        held_after = [
            (day, positions)
            for day, positions in output.positions_by_date.items()
            if day > cut + timedelta(days=7) and positions.get("S00", 0) > 0
        ]
        assert not held_after, "delisted symbol still held after data ended"


class TestMonthlyRebalance:
    def test_monthly_trades_fewer_than_weekly(self):
        weekly = build_engine(trending_universe(), rebalance_frequency="weekly").run()
        monthly = build_engine(trending_universe(), rebalance_frequency="monthly").run()
        assert len(monthly.trades) <= len(weekly.trades)
