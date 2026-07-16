"""Strategy protocol. Strategies emit target weights, never orders, and have
no access to broker clients or credentials by construction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.strategy import StrategyContext, StrategyResult


@runtime_checkable
class Strategy(Protocol):
    name: str
    version: str

    def generate_target_portfolio(self, context: StrategyContext) -> StrategyResult: ...
