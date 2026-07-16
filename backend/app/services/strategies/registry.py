"""Strategy registry: maps names to constructors."""

from __future__ import annotations

from app.services.strategies.base import Strategy
from app.services.strategies.weekly_multi_factor import WeeklyMultiFactorTrendStrategy

_REGISTRY: dict[str, type] = {
    WeeklyMultiFactorTrendStrategy.name: WeeklyMultiFactorTrendStrategy,
}


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)


def build_strategy(name: str, parameters: dict | None = None) -> Strategy:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown strategy: {name!r}. Available: {available_strategies()}")
    return cls(parameters=parameters)  # type: ignore[no-any-return]
