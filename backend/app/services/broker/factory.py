"""Broker factory. There is deliberately no branch that returns a live client."""

from __future__ import annotations

from app.config import Settings
from app.services.broker.base import BrokerClient
from app.services.broker.mock_broker import MockBrokerClient


def build_broker(settings: Settings) -> BrokerClient:
    if settings.live_trading_enabled:
        # Unreachable in practice (Settings validation rejects it) — kept as
        # defense in depth so a bypassed config still cannot construct a broker.
        raise RuntimeError("Live trading is permanently disabled in this build.")
    if settings.broker_provider == "alpaca_paper":
        from app.services.broker.alpaca_paper import AlpacaPaperBrokerClient

        return AlpacaPaperBrokerClient(settings)
    # Default deterministic mock with a small ETF universe.
    prices = {
        "SPY": 500.0, "QQQ": 430.0, "IWM": 210.0, "EFA": 78.0, "AGG": 98.0,
        "GLD": 215.0, "VNQ": 88.0, "XLE": 92.0, "TLT": 93.0, "DOWN": 40.0,
    }
    return MockBrokerClient(starting_cash=100_000.0, prices=prices)
