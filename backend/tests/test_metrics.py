"""Performance-metrics tests, including divide-by-zero and short-sample cases."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.backtesting import metrics as m


def dates(n: int) -> list[date]:
    start = date(2025, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


class TestBasics:
    def test_total_return(self):
        assert m.total_return([100, 110]) == pytest.approx(0.10)

    def test_total_return_insufficient(self):
        assert m.total_return([100]) is None
        assert m.total_return([]) is None

    def test_annualized_return_one_year(self):
        equity = [100 * (1.0004**i) for i in range(253)]
        ann = m.annualized_return(equity)
        assert ann == pytest.approx(1.0004**252 - 1, rel=1e-6)

    def test_max_drawdown(self):
        assert m.max_drawdown([100, 120, 60, 90]) == pytest.approx(-0.5)

    def test_max_drawdown_monotonic(self):
        assert m.max_drawdown([100, 110, 120]) == pytest.approx(0.0)

    def test_drawdown_series_shape(self):
        series = m.drawdown_series([100, 120, 60])
        assert series == [0.0, 0.0, pytest.approx(-0.5)]


class TestRatios:
    def test_sharpe_suppressed_on_short_sample(self):
        assert m.sharpe_ratio([0.001] * 10) is None

    def test_sharpe_zero_variance_is_none(self):
        assert m.sharpe_ratio([0.0] * 100) is None

    def test_sharpe_positive_for_positive_drift(self):
        returns = [0.001 + (0.002 if i % 2 else -0.002) for i in range(252)]
        sharpe = m.sharpe_ratio(returns)
        assert sharpe is not None and sharpe > 0

    def test_sortino_none_without_downside(self):
        # All positive returns → downside deviation 0 → None, not inf.
        assert m.sortino_ratio([0.001] * 100) is None

    def test_calmar_none_without_drawdown(self):
        equity = [100 + i for i in range(300)]
        assert m.calmar_ratio(equity) is None

    def test_beta_alpha_vs_self(self):
        returns = [0.001 * ((i % 5) - 2) for i in range(200)]
        beta, alpha = m.beta_alpha(returns, returns)
        assert beta == pytest.approx(1.0)
        assert alpha == pytest.approx(0.0, abs=1e-9)

    def test_beta_none_on_flat_benchmark(self):
        beta, alpha = m.beta_alpha([0.001] * 100, [0.0] * 100)
        assert beta is None and alpha is None

    def test_tracking_error_zero_for_identical(self):
        returns = [0.001 * ((i % 7) - 3) for i in range(200)]
        te = m.tracking_error(returns, returns)
        assert te == pytest.approx(0.0, abs=1e-12)


class TestComputeMetrics:
    def test_short_backtest_warns_and_suppresses(self):
        ds = dates(10)
        equity = [100.0 + i for i in range(10)]
        metrics, warnings = m.compute_metrics(ds, equity, None, [])
        assert warnings, "short sample must produce a warning"
        assert metrics["sharpe_ratio"] is None
        assert metrics["total_return"] is not None

    def test_trade_stats(self):
        ds = dates(100)
        equity = [100.0 + i * 0.1 for i in range(100)]
        trades = [
            {"notional": 1000, "realized_pl": 50, "holding_days": 10},
            {"notional": 1000, "realized_pl": -20, "holding_days": 5},
            {"notional": 500, "realized_pl": 30, "holding_days": 20},
            {"notional": 700, "realized_pl": None, "holding_days": None},  # open
        ]
        metrics, _ = m.compute_metrics(ds, equity, None, trades)
        assert metrics["number_of_trades"] == 4
        assert metrics["win_rate"] == pytest.approx(2 / 3)
        assert metrics["average_gain"] == pytest.approx(40)
        assert metrics["average_loss"] == pytest.approx(-20)
        assert metrics["profit_factor"] == pytest.approx(80 / 20)
        assert metrics["average_holding_period_days"] == pytest.approx(35 / 3)

    def test_profit_factor_none_without_losses(self):
        ds = dates(100)
        equity = [100.0] * 100
        trades = [{"notional": 100, "realized_pl": 10, "holding_days": 1}]
        metrics, _ = m.compute_metrics(ds, equity, None, trades)
        assert metrics["profit_factor"] is None

    def test_benchmark_and_excess(self):
        ds = dates(100)
        equity = [100.0 * (1.001**i) for i in range(100)]
        bench = [100.0 * (1.0005**i) for i in range(100)]
        metrics, _ = m.compute_metrics(ds, equity, bench, [])
        assert metrics["benchmark_return"] is not None
        assert metrics["excess_return"] == pytest.approx(
            metrics["total_return"] - metrics["benchmark_return"]
        )

    def test_best_worst_month(self):
        ds = [date(2025, 1, 1) + timedelta(days=i) for i in range(90)]
        equity = []
        value = 100.0
        for d in ds:
            value *= 1.002 if d.month == 1 else (0.999 if d.month == 2 else 1.001)
            equity.append(value)
        metrics, _ = m.compute_metrics(ds, equity, None, [])
        assert metrics["best_month"] is not None
        assert metrics["worst_month"] is not None
        assert metrics["best_month"] > metrics["worst_month"]
