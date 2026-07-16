"""Verify the configured broker connection (read-only; places no orders).

Run from backend/:  python ../scripts/verify_broker_connection.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.logging import configure_logging  # noqa: E402
from app.services.broker.factory import build_broker  # noqa: E402


async def main() -> int:
    configure_logging()
    settings = get_settings()
    print(f"Broker provider: {settings.broker_provider} (paper only)")
    try:
        broker = build_broker(settings)
    except Exception as exc:
        print(f"FAILED to construct broker client: {exc}")
        return 1
    try:
        account = await broker.get_account()
        clock = await broker.get_market_clock()
        positions = await broker.get_positions()
    except Exception as exc:
        print(f"FAILED to reach broker: {exc}")
        return 1
    masked = account.account_id[:2] + "..." + account.account_id[-2:]
    print(f"Connected. account={masked} paper={account.is_paper}")
    print(f"equity=${account.equity:,.2f} cash=${account.cash:,.2f}")
    print(f"market_open={clock.is_open} positions={len(positions)}")
    print("No orders were placed. Verification complete.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
