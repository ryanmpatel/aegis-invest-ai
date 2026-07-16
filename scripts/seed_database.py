"""Seed the database with a default universe, risk profile, strategy, and
synthetic market data from the mock provider.

Run from backend/:  python ../scripts/seed_database.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.database import get_engine, get_session_factory  # noqa: E402
from app.logging import configure_logging  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.config import (  # noqa: E402
    ApprovedUniverse,
    RiskProfile,
    SchedulerConfig,
    StrategyDefinition,
    StrategyVersion,
)
from app.schemas.risk import RiskLimits  # noqa: E402
from app.services.market_data.mock_provider import MockMarketDataProvider  # noqa: E402
from app.services.market_data.store import upsert_asset, upsert_bars  # noqa: E402
from app.services.strategies.weekly_multi_factor import (  # noqa: E402
    WeeklyMultiFactorTrendStrategy,
)
from app.utils.timeutils import utcnow  # noqa: E402

DEFAULT_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "AGG", "GLD", "VNQ", "XLE"]


async def main() -> None:
    configure_logging()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with get_session_factory()() as session:
        existing = (
            await session.execute(select(ApprovedUniverse).limit(1))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ApprovedUniverse(name="default", symbols=DEFAULT_UNIVERSE, is_active=True)
            )
            print(f"Seeded universe: {DEFAULT_UNIVERSE}")

        if (await session.execute(select(RiskProfile).limit(1))).scalar_one_or_none() is None:
            session.add(
                RiskProfile(
                    name="conservative-defaults",
                    limits=RiskLimits().model_dump(),
                    is_active=True,
                )
            )
            print("Seeded conservative default risk profile.")

        if (
            await session.execute(select(StrategyDefinition).limit(1))
        ).scalar_one_or_none() is None:
            strategy = WeeklyMultiFactorTrendStrategy()
            definition = StrategyDefinition(
                name="Weekly Multi-Factor Trend",
                description=(
                    "Educational starter strategy: trend eligibility (price and "
                    "50d SMA above 200d SMA), momentum/trend scoring with "
                    "volatility and drawdown penalties, inverse-volatility "
                    "weights, weekly rebalance. Not a claim of profitability."
                ),
                is_active=True,
            )
            session.add(definition)
            await session.flush()
            session.add(
                StrategyVersion(
                    definition_id=definition.id,
                    version=strategy.version,
                    parameters=dict(strategy.parameters),
                )
            )
            print("Seeded Weekly Multi-Factor Trend strategy.")

        if (
            await session.execute(select(SchedulerConfig).limit(1))
        ).scalar_one_or_none() is None:
            session.add(SchedulerConfig())
            print("Seeded scheduler config (disabled).")

        provider = MockMarketDataProvider()
        end = utcnow().date()
        start = end - timedelta(days=750)
        bars_by_symbol = await provider.get_daily_bars(DEFAULT_UNIVERSE, start, end)
        total = 0
        for symbol, bars in bars_by_symbol.items():
            total += await upsert_bars(session, symbol, bars)
            asset = await provider.get_asset(symbol)
            if asset:
                await upsert_asset(session, asset)
        print(f"Stored {total} synthetic daily bars for {len(bars_by_symbol)} symbols.")

        await session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
