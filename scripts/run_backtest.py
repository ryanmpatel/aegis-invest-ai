"""Run a sample backtest from the command line.

Run from backend/:  python ../scripts/run_backtest.py [--start YYYY-MM-DD]
                    [--end YYYY-MM-DD] [--capital 100000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import get_engine, get_session_factory  # noqa: E402
from app.logging import configure_logging  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.backtesting.runner import make_config, run_backtest  # noqa: E402
from app.services.market_data.mock_provider import MockMarketDataProvider  # noqa: E402
from app.utils.timeutils import utcnow  # noqa: E402

DEFAULT_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "AGG", "GLD", "VNQ", "XLE"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    today = utcnow().date()
    parser.add_argument("--start", default=str(today - timedelta(days=365 * 2)))
    parser.add_argument("--end", default=str(today - timedelta(days=1)))
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--universe", nargs="*", default=DEFAULT_UNIVERSE)
    args = parser.parse_args()

    configure_logging()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    config = make_config({
        "start": args.start,
        "end": args.end,
        "starting_capital": args.capital,
        "universe": args.universe,
        "benchmark_symbol": "SPY",
    })
    async with get_session_factory()() as session:
        run = await run_backtest(
            session, MockMarketDataProvider(),
            strategy_name="weekly_multi_factor_trend",
            strategy_parameters=None,
            config=config,
        )
        await session.commit()

    print(f"\nBacktest {run.id}: {run.status}")
    print(json.dumps(run.metrics, indent=2, default=str))
    if run.warnings:
        print("\nWarnings:")
        for warning in run.warnings:
            print(f"  - {warning}")
    print(
        "\nNote: synthetic mock data; results are illustrative only and are "
        "not a claim of real-world performance."
    )


if __name__ == "__main__":
    asyncio.run(main())
