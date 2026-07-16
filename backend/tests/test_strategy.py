"""Weekly Multi-Factor Trend strategy tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.strategy import StrategyContext
from app.services.strategies.weekly_multi_factor import WeeklyMultiFactorTrendStrategy
from tests.helpers import make_bars

AS_OF = datetime.now(UTC)


def context(bars_map, tradable=None, ai_flags=None, universe=None) -> StrategyContext:
    return StrategyContext(
        as_of=AS_OF,
        universe=universe or list(bars_map),
        bars=bars_map,
        tradable=tradable or dict.fromkeys(bars_map, True),
        ai_risk_flags=ai_flags or {},
    )


def uptrend(symbol: str, seed: int = 1):
    return make_bars(symbol, 260, daily_return=0.0008, volatility=0.008, seed=seed)


def downtrend(symbol: str):
    return make_bars(symbol, 260, daily_return=-0.002, volatility=0.008)


class TestEligibility:
    def test_uptrending_symbol_selected(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"AAA": uptrend("AAA")})
        )
        ev = result.evaluations[0]
        assert ev.eligible
        assert ev.score is not None and 0 <= ev.score <= 1
        assert result.portfolio.targets and result.portfolio.targets[0].symbol == "AAA"

    def test_downtrend_excluded_below_200sma(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"BBB": downtrend("BBB")})
        )
        ev = result.evaluations[0]
        assert not ev.eligible
        assert any("200d_sma" in r or "price_below" in r for r in ev.exclusion_reasons)
        assert not result.portfolio.targets

    def test_insufficient_history_excluded(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"CCC": make_bars("CCC", 50, daily_return=0.001)})
        )
        ev = result.evaluations[0]
        assert not ev.eligible
        assert any("insufficient_history" in r for r in ev.exclusion_reasons)

    def test_not_tradable_excluded(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"DDD": uptrend("DDD")}, tradable={"DDD": False})
        )
        assert not result.evaluations[0].eligible
        assert "not_tradable" in result.evaluations[0].exclusion_reasons

    def test_illiquid_excluded(self):
        bars = make_bars("EEE", 260, daily_return=0.0008, volume=1_000)
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"EEE": bars})
        )
        assert not result.evaluations[0].eligible
        assert "insufficient_liquidity" in result.evaluations[0].exclusion_reasons

    def test_cheap_stock_excluded(self):
        bars = make_bars("FFF", 260, start_price=2.0, daily_return=0.0008,
                         volume=50_000_000)
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"FFF": bars})
        )
        assert not result.evaluations[0].eligible
        assert any("below_min_price" in r for r in result.evaluations[0].exclusion_reasons)

    def test_critical_ai_flag_excluded(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"GGG": uptrend("GGG")}, ai_flags={"GGG": "critical"})
        )
        assert not result.evaluations[0].eligible
        assert "critical_ai_risk_flag" in result.evaluations[0].exclusion_reasons


class TestScoringAndWeights:
    def test_score_breakdown_persisted(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"AAA": uptrend("AAA")})
        )
        breakdown = result.evaluations[0].score_breakdown
        assert breakdown is not None
        assert 0 <= breakdown.total <= 1
        assert breakdown.momentum_medium > 0.5  # positive momentum
        assert result.evaluations[0].score == breakdown.total

    def test_weights_within_bounds(self):
        bars_map = {f"S{i:02d}": uptrend(f"S{i:02d}", seed=i) for i in range(10)}
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context(bars_map)
        )
        portfolio = result.portfolio
        total = sum(t.target_weight for t in portfolio.targets)
        assert total <= 1.0 + 1e-6
        assert portfolio.cash_target == pytest.approx(1.0 - total, abs=1e-4)
        for t in portfolio.targets:
            assert t.target_weight <= 0.20 + 1e-9  # max_position_weight

    def test_max_positions_respected(self):
        bars_map = {f"S{i:02d}": uptrend(f"S{i:02d}", seed=i) for i in range(12)}
        strategy = WeeklyMultiFactorTrendStrategy({"max_positions": 3})
        result = strategy.generate_target_portfolio(context(bars_map))
        assert len(result.portfolio.targets) <= 3

    def test_inverse_volatility_weighting(self):
        low_vol = make_bars("LOW", 260, daily_return=0.0008, volatility=0.004, seed=3)
        high_vol = make_bars("HIGH", 260, daily_return=0.0008, volatility=0.03, seed=4)
        strategy = WeeklyMultiFactorTrendStrategy({"max_position_weight": 0.9,
                                                   "min_score": 0.0})
        result = strategy.generate_target_portfolio(
            context({"LOW": low_vol, "HIGH": high_vol})
        )
        weights = {t.symbol: t.target_weight for t in result.portfolio.targets}
        assert set(weights) == {"LOW", "HIGH"}
        assert weights["LOW"] > weights["HIGH"]

    def test_reasons_are_human_readable(self):
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(
            context({"AAA": uptrend("AAA")})
        )
        reasons = result.portfolio.targets[0].reasons
        assert any("200-day moving average" in r for r in reasons)
