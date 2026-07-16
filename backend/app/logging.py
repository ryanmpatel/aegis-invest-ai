"""Structured JSON logging with secret redaction and correlation IDs.

Every major event carries: correlation_id, component, event_type, severity,
timestamp, plus optional strategy_run_id / account_snapshot_id / symbol.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.utils.redaction import redact

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
strategy_run_id_var: ContextVar[str | None] = ContextVar("strategy_run_id", default=None)

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        cid = correlation_id_var.get()
        if cid:
            payload["correlation_id"] = cid
        run_id = strategy_run_id_var.get()
        if run_id:
            payload["strategy_run_id"] = run_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(redact(payload), default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    # Quiet noisy libraries; our own events matter more.
    for noisy in ("uvicorn.access", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(component)


def log_event(
    logger: logging.Logger,
    event_type: str,
    message: str,
    *,
    severity: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log a structured audit event. Extra fields are redacted and serialized."""
    logger.log(severity, message, extra={"event_type": event_type, **fields})
