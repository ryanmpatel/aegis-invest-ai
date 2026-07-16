"""Every risk rule, tested individually."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.risk import (
    AccountState,
    MarketContext,
    RiskAction,
    RiskLimits,
    TradeIntent,
)
from app.services.risk.engine import RiskEngine

NOW = datetime.now(UTC)


def account(**overrides) -> AccountState:
    defaults = dict(
        equity=100_000.0, cash=50_000.0, buying_power=50_000.0,
        positions={}, position_values={},
    )
    return AccountState(**{**defaults, **overrides})


def market(**overrides) -> MarketContext:
    defaults = dict(
        prices={"SPY": 500.0},
        price_timestamps={"SPY": NOW},
        tradable={"SPY": True},
        avg_daily_volumes={"SPY": 10_000_000},
        approved_universe=["SPY"],
        now=NOW,
    )
    return MarketContext(**{**defaults, **overrides})


def buy(notional: float = 5_000.0, symbol: str = "SPY", price: float = 500.0) -> TradeIntent:
    return TradeIntent(
        symbol=symbol, side="buy", quantity=notional / price,
        notional=notional, reference_price=price,
    )


def sell(quantity: float, symbol: str = "SPY", price: float = 500.0) -> TradeIntent:
    return TradeIntent(
        symbol=symbol, side="sell", quantity=quantity,
        notional=quantity * price, reference_price=price,
    )


class TestApproval:
    def test_reasonable_buy_approved(self):
        verdict = RiskEngine().review_trade(buy(), account(), market())
        assert verdict.action == RiskAction.APPROVE
        assert verdict.approved_notional == pytest.approx(5_000.0)

    def test_sell_of_held_position_approved(self):
        acct = account(positions={"SPY": 20}, position_values={"SPY": 10_000})
        verdict = RiskEngine().review_trade(sell(10), acct, market())
        assert verdict.action == RiskAction.APPROVE


class TestPositionRules:
    def test_min_price_rejected(self):
        ctx = market(prices={"SPY": 3.0}, avg_daily_volumes={"SPY": 10_000_000})
        verdict = RiskEngine().review_trade(buy(1000, price=3.0), account(), ctx)
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "min_price"
        assert verdict.actual_value == 3.0
        assert verdict.limit_value == RiskLimits().min_price

    def test_non_tradable_rejected(self):
        ctx = market(tradable={"SPY": False})
        verdict = RiskEngine().review_trade(buy(), account(), ctx)
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "tradable_asset"

    def test_outside_universe_rejected(self):
        ctx = market(approved_universe=["QQQ"])
        verdict = RiskEngine().review_trade(buy(), account(), ctx)
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "approved_universe"

    def test_stale_price_rejected(self):
        ctx = market(price_timestamps={"SPY": NOW - timedelta(days=10)})
        verdict = RiskEngine().review_trade(buy(), account(), ctx)
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "stale_price"

    def test_missing_price_rejected(self):
        ctx = market(prices={})
        verdict = RiskEngine().review_trade(buy(), account(), ctx)
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "known_price"

    def test_max_position_pct_resizes(self):
        # 15% of 100k = 15k cap; ask for 20k.
        verdict = RiskEngine().review_trade(buy(20_000), account(), market())
        assert verdict.action == RiskAction.RESIZE
        assert verdict.approved_notional <= 15_000 + 1e-6

    def test_max_order_notional_resizes(self):
        limits = RiskLimits(max_order_notional=2_000)
        verdict = RiskEngine(limits).review_trade(buy(5_000), account(), market())
        assert verdict.action == RiskAction.RESIZE
        assert verdict.approved_notional <= 2_000 + 1e-6

    def test_min_order_value_rejects_tiny_trade(self):
        verdict = RiskEngine().review_trade(buy(50), account(), market())
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "min_order_value"

    def test_adv_limit_resizes(self):
        ctx = market(avg_daily_volumes={"SPY": 1_000})  # 1% of ADV = 10 shares
        verdict = RiskEngine().review_trade(buy(10_000), account(), ctx)
        assert verdict.action == RiskAction.RESIZE
        assert verdict.approved_quantity <= 10 + 1e-6


class TestAccountRules:
    def test_no_shorting_rejects_unheld_sell(self):
        verdict = RiskEngine().review_trade(sell(10), account(), market())
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "no_shorting"

    def test_oversized_sell_resized_to_held(self):
        acct = account(positions={"SPY": 5}, position_values={"SPY": 2_500})
        verdict = RiskEngine().review_trade(sell(10), acct, market())
        assert verdict.action == RiskAction.RESIZE
        assert verdict.approved_quantity == pytest.approx(5)

    def test_cash_reserve_respected(self):
        # equity 100k, cash 6k, reserve 5% (5k) → only ~1k headroom.
        acct = account(cash=6_000, positions={"QQQ": 100},
                       position_values={"QQQ": 94_000})
        verdict = RiskEngine().review_trade(buy(5_000), acct, market())
        assert verdict.action in (RiskAction.RESIZE, RiskAction.REJECT)
        if verdict.action == RiskAction.RESIZE:
            assert verdict.approved_notional <= 1_000 + 1e-6

    def test_max_open_positions_rejected(self):
        limits = RiskLimits(max_open_positions=2)
        acct = account(
            positions={"QQQ": 1, "IWM": 1},
            position_values={"QQQ": 400, "IWM": 200},
        )
        verdict = RiskEngine(limits).review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.REJECT
        assert verdict.rule_name == "max_open_positions"

    def test_new_capital_per_rebalance_capped(self):
        limits = RiskLimits(max_new_capital_per_rebalance_pct=0.10)
        verdict = RiskEngine(limits).review_trade(
            buy(9_000), account(), market(), planned_buy_notional_before=8_000
        )
        assert verdict.action in (RiskAction.RESIZE, RiskAction.REJECT)
        if verdict.action == RiskAction.RESIZE:
            assert verdict.approved_notional <= 2_000 + 1e-6

    def test_daily_turnover_capped(self):
        limits = RiskLimits(max_daily_turnover_pct=0.10)
        verdict = RiskEngine(limits).review_trade(
            buy(8_000), account(), market(), planned_turnover_before=9_500
        )
        assert verdict.action in (RiskAction.RESIZE, RiskAction.REJECT)
        if verdict.action == RiskAction.RESIZE:
            assert verdict.approved_notional <= 500 + 1e-6


class TestFreezeConditions:
    def test_daily_loss_limit_freezes(self):
        acct = account(daily_pl_pct=-0.05)
        verdict = RiskEngine().review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.FREEZE
        assert verdict.rule_name == "daily_loss_limit"

    def test_drawdown_limit_freezes(self):
        acct = account(drawdown_pct=-0.20)
        verdict = RiskEngine().review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.FREEZE
        assert verdict.rule_name == "strategy_drawdown_limit"

    def test_consecutive_errors_freeze(self):
        acct = account(consecutive_errors=3)
        verdict = RiskEngine().review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.FREEZE

    def test_consecutive_rejections_freeze(self):
        acct = account(consecutive_rejected_orders=5)
        verdict = RiskEngine().review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.FREEZE

    def test_nan_equity_freezes(self):
        acct = account(equity=float("nan"))
        verdict = RiskEngine().review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.FREEZE
        assert verdict.rule_name == "non_finite_account_value"

    def test_volatility_limit_freezes(self):
        acct = account(portfolio_volatility=0.50)
        verdict = RiskEngine().review_trade(buy(), acct, market())
        assert verdict.action == RiskAction.FREEZE


class TestRejectionRecordKeeping:
    def test_rejection_records_rule_value_and_limit(self):
        ctx = market(prices={"SPY": 3.0})
        verdict = RiskEngine().review_trade(buy(1000, price=3.0), account(), ctx)
        assert verdict.rule_name == "min_price"
        assert verdict.actual_value is not None
        assert verdict.limit_value is not None
        assert any(not c.passed for c in verdict.checks)
