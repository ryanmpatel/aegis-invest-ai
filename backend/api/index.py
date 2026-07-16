"""Vercel serverless entrypoint for the AegisInvest backend.

Serverless notes:
- The scheduler is forced off (each invocation is short-lived; use the
  dashboard's "Run rebalance once" instead).
- Tables are created idempotently at cold start (Alembic isn't practical
  here, and `create_all(checkfirst=True)` is safe to run repeatedly).
- Live trading remains disabled exactly as everywhere else.
"""

from __future__ import annotations

import os

os.environ.setdefault("SCHEDULER_ENABLED", "false")

from app.logging import configure_logging, get_logger  # noqa: E402

configure_logging()
logger = get_logger("vercel.bootstrap")


def _ensure_tables() -> None:
    try:
        from sqlalchemy import create_engine

        from app.config import get_settings
        from app.database import normalize_database_url
        from app.models import Base

        sync_url = normalize_database_url(get_settings().database_url, driver="sync")
        engine = create_engine(sync_url, pool_pre_ping=True)
        Base.metadata.create_all(engine, checkfirst=True)
        engine.dispose()
    except Exception:
        # Requests will surface database errors; don't block startup on this.
        logger.warning("table bootstrap failed", exc_info=True)


_ensure_tables()

from app.main import create_app  # noqa: E402

app = create_app()
