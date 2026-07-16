"""Vercel serverless entrypoint for the AegisInvest backend.

Serverless notes:
- The scheduler is forced off (each invocation is short-lived; use the
  dashboard's "Run rebalance once" instead).
- Missing tables are created by the app's startup lifespan (idempotent,
  sentinel-checked), which runs on this runtime.
- Live trading remains disabled exactly as everywhere else.
"""

from __future__ import annotations

import os

os.environ.setdefault("SCHEDULER_ENABLED", "false")

from app.logging import configure_logging  # noqa: E402

configure_logging()

from app.main import create_app  # noqa: E402

app = create_app()
