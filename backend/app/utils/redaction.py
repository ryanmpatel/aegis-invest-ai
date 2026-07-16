"""Secret redaction for logs and notifications.

Redacts values whose keys look secret-bearing, and scrubs strings that match
known credential shapes (Alpaca keys, bearer tokens, etc.).
"""

from __future__ import annotations

import re
from typing import Any

_SECRET_KEY_PATTERN = re.compile(
    r"(secret|password|passwd|token|api[-_]?key|authorization|credential|cookie)",
    re.IGNORECASE,
)
# Alpaca-style keys (PK/AK + 16-20 chars), long hex/base64 blobs, bearer tokens.
_SECRET_VALUE_PATTERNS = [
    re.compile(r"\b[PA]K[A-Z0-9]{16,20}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9\-_]{16,}\b"),
]

REDACTED = "[REDACTED]"


def _scrub_string(value: str) -> str:
    for pattern in _SECRET_VALUE_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact(value: Any) -> Any:
    """Recursively redact secrets from dicts, lists and strings."""
    if isinstance(value, dict):
        return {
            k: REDACTED if _SECRET_KEY_PATTERN.search(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _scrub_string(value)
    return value
