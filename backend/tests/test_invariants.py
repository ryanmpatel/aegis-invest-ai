"""Property/invariant tests (hypothesis)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from app.config import Settings
from app.schemas.risk import AccountState, MarketContext, RiskAction, TradeIntent
from app.schemas.strategy import StrategyContext, TargetPortfolio, TargetWeight
from app.services.risk.engine import RiskEngine
from app.services.strategies.weekly_multi_factor import WeeklyMultiFactorTrendStrategy
from tests.helpers import make_bars

NOW = datetime.now(UTC)


class TestPortfolioWeightInvariant:
    def test_target_portfolio_rejects_weights_over_one(self):
        with pytest.raises(ValueError):
            TargetPortfolio(
                strategy_name="x", strategy_version="1", as_of=NOW,
                targets=[
                    TargetWeight(symbol="A", target_weight=0.6),
                    TargetWeight(symbol="B", target_weight=0.6),
                ],
                cash_target=0.0,
            )

    @hyp_settings(max_examples=25, deadline=None)
    @given(
        n=st.integers(min_value=1, max_value=8),
        drift=st.floats(min_value=-0.003, max_value=0.003),
        vol=st.floats(min_value=0.0, max_value=0.03),
    )
    def test_strategy_weights_never_exceed_one(self, n, drift, vol):
        bars_map = {
            f"S{i}": make_bars(f"S{i}", 260, daily_return=drift, volatility=vol, seed=i)
            for i in range(n)
        }
        context = StrategyContext(
            as_of=NOW, universe=list(bars_map), bars=bars_map,
            tradable=dict.fromkeys(bars_map, True),
        )
        result = WeeklyMultiFactorTrendStrategy().generate_target_portfolio(context)
        total = sum(t.target_weight for t in result.portfolio.targets)
        assert total <= 1.0 + 1e-6
        assert result.portfolio.cash_target >= -1e-9


class TestRiskEngineInvariants:
    @hyp_settings(max_examples=100, deadline=None)
    @given(
        notional=st.floats(min_value=1, max_value=1_000_000),
        cash=st.floats(min_value=0, max_value=500_000),
        equity=st.floats(min_value=1_000, max_value=1_000_000),
        price=st.floats(min_value=0.5, max_value=5_000),
    )
    def test_approved_buys_never_violate_core_limits(self, notional, cash, equity, price):
        engine = RiskEngine()
        limits = engine.limits
        account = AccountState(
            equity=equity, cash=min(cash, equity), buying_power=min(cash, equity),
            positions={}, position_values={},
        )
        market = MarketContext(
            prices={"SPY": price}, price_timestamps={"SPY": NOW},
            tradable={"SPY": True}, avg_daily_volumes={"SPY": 1e9},
            approved_universe=["SPY"], now=NOW,
        )
        intent = TradeIntent(
            symbol="SPY", side="buy", quantity=notional / price,
            notional=notional, reference_price=price,
        )
        verdict = engine.review_trade(intent, account, market)
        if verdict.action in (RiskAction.APPROVE, RiskAction.RESIZE):
            approved = verdict.approved_notional
            assert approved <= limits.max_order_notional + 1e-6
            assert approved <= limits.max_position_pct * equity + 1e-6
            assert approved <= account.cash + 1e-6          # never leverage
            assert approved >= limits.min_order_notional - 1e-6
            assert price >= limits.min_price

    @hyp_settings(max_examples=50, deadline=None)
    @given(
        held=st.floats(min_value=0, max_value=1_000),
        sell_qty=st.floats(min_value=0.01, max_value=5_000),
    )
    def test_never_creates_short_position(self, held, sell_qty):
        engine = RiskEngine()
        account = AccountState(
            equity=1_000_000, cash=500_000, buying_power=500_000,
            positions={"SPY": held}, position_values={"SPY": held * 500.0},
        )
        market = MarketContext(
            prices={"SPY": 500.0}, price_timestamps={"SPY": NOW},
            tradable={"SPY": True}, avg_daily_volumes={"SPY": 1e9},
            approved_universe=["SPY"], now=NOW,
        )
        intent = TradeIntent(
            symbol="SPY", side="sell", quantity=sell_qty,
            notional=sell_qty * 500.0, reference_price=500.0,
        )
        verdict = engine.review_trade(intent, account, market)
        if verdict.action in (RiskAction.APPROVE, RiskAction.RESIZE):
            assert verdict.approved_quantity <= held + 1e-6


class TestLiveTradingCannotInitialize:
    def test_settings_reject_live_flag(self, monkeypatch):
        monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
        with pytest.raises(Exception, match=r"disabled|not supported"):
            Settings()

    def test_broker_factory_has_no_live_branch(self):
        import inspect

        from app.services.broker import factory

        source = inspect.getsource(factory)
        assert "live" not in source.lower().replace(
            "live trading is permanently disabled", ""
        ).replace("live_trading_enabled", "").replace("live client", ""), (
            "factory must not grow a live-broker branch"
        )

    def test_alpaca_requires_paper_credentials(self, monkeypatch):
        monkeypatch.setenv("BROKER_PROVIDER", "alpaca_paper")
        monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_PAPER_API_SECRET", raising=False)
        with pytest.raises(Exception, match=r"paper credentials|ALPACA_PAPER"):
            Settings()


class TestSecretsHygiene:
    def test_settings_repr_hides_secrets(self, monkeypatch):
        monkeypatch.setenv("ALPACA_PAPER_API_KEY", "PKSECRETSECRETSECRET")
        monkeypatch.setenv("APP_SECRET_KEY", "supersecretvalue123")
        settings = Settings()
        dump = repr(settings) + str(settings)
        assert "PKSECRETSECRETSECRET" not in dump
        assert "supersecretvalue123" not in dump

    def test_redaction_scrubs_alpaca_keys(self):
        from app.utils.redaction import redact

        payload = {
            "message": "using key PKABCDEFGHIJKLMNOP12 for auth",
            "api_key": "raw-value",
            "nested": {"password": "hunter2", "ok": "fine"},
        }
        cleaned = redact(payload)
        assert "PKABCDEFGHIJKLMNOP12" not in cleaned["message"]
        assert cleaned["api_key"] == "[REDACTED]"
        assert cleaned["nested"]["password"] == "[REDACTED]"
        assert cleaned["nested"]["ok"] == "fine"
