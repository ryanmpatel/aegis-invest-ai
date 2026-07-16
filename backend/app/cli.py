"""Command-line utilities, most importantly the kill switch.

Usage:
    python -m app.cli kill-switch --activate --reason "why"
    python -m app.cli kill-switch --deactivate --reason "why"
    python -m app.cli kill-switch --status
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from app.database import get_session_factory
from app.logging import configure_logging
from app.services.risk.kill_switch import (
    get_kill_switch_state,
    set_kill_switch,
)


async def _kill_switch(args: argparse.Namespace) -> int:
    async with get_session_factory()() as session:
        if args.status:
            state = await get_kill_switch_state(session)
            if state is None:
                print("Kill switch: never activated (inactive)")
            else:
                print(
                    f"Kill switch: {'ACTIVE' if state.active else 'inactive'} "
                    f"(last change by {state.actor} at {state.created_at}: {state.reason})"
                )
            return 0
        if args.activate == args.deactivate:
            print("Specify exactly one of --activate / --deactivate (or --status).")
            return 2
        actor = f"cli:{getpass.getuser()}"
        event = await set_kill_switch(
            session,
            active=bool(args.activate),
            actor=actor,
            reason=args.reason or "CLI invocation",
        )
        await session.commit()
        print(
            f"Kill switch {'ACTIVATED' if event.active else 'deactivated'} by {actor}. "
            "Note: open buy orders are canceled on the next backend safety sweep; "
            "order submission is blocked immediately."
        )
        return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="aegis")
    sub = parser.add_subparsers(dest="command", required=True)

    ks = sub.add_parser("kill-switch", help="Control the trading kill switch")
    ks.add_argument("--activate", action="store_true")
    ks.add_argument("--deactivate", action="store_true")
    ks.add_argument("--status", action="store_true")
    ks.add_argument("--reason", default="")

    args = parser.parse_args(argv)
    if args.command == "kill-switch":
        return asyncio.run(_kill_switch(args))
    return 2


if __name__ == "__main__":
    sys.exit(main())
