"""Password hashing and signed session tokens (stdlib only).

Passwords: PBKDF2-HMAC-SHA256 with per-hash random salt.
Sessions:  HMAC-signed, expiring tokens stored in an HttpOnly cookie.
CSRF:      random token issued alongside the session, double-submit checked.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

_PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_s, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations_s))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _sign(payload: bytes, secret: str) -> str:
    return base64.urlsafe_b64encode(
        hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    ).decode().rstrip("=")


def create_session_token(username: str, secret: str, ttl_minutes: int) -> tuple[str, str]:
    """Return (session_token, csrf_token)."""
    csrf_token = secrets.token_urlsafe(32)
    payload_dict: dict[str, Any] = {
        "sub": username,
        "exp": (datetime.now(UTC) + timedelta(minutes=ttl_minutes)).timestamp(),
        "csrf": csrf_token,
        "nonce": secrets.token_urlsafe(8),
    }
    payload = base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload.encode(), secret)}", csrf_token


def verify_session_token(token: str, secret: str) -> dict[str, Any] | None:
    """Return the payload if the token is valid and unexpired, else None."""
    try:
        payload_b64, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(signature, _sign(payload_b64.encode(), secret)):
            return None
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
        if datetime.now(UTC).timestamp() > float(payload["exp"]):
            return None
        return payload
    except (ValueError, KeyError, TypeError):
        return None
