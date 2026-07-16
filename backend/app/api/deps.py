"""API dependencies: authentication, CSRF, rate limiting, shared providers."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.services.broker.base import BrokerClient
from app.services.broker.factory import build_broker
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.utils.rate_limit import SlidingWindowRateLimiter
from app.utils.security import verify_session_token

_rate_limiters: dict[str, SlidingWindowRateLimiter] = {}
_broker_singleton: BrokerClient | None = None
_market_data_singleton: MarketDataProvider | None = None


def get_rate_limiter(name: str, limit: int) -> SlidingWindowRateLimiter:
    if name not in _rate_limiters:
        _rate_limiters[name] = SlidingWindowRateLimiter(limit)
    return _rate_limiters[name]


def reset_singletons() -> None:
    """Test helper."""
    global _broker_singleton, _market_data_singleton
    _broker_singleton = None
    _market_data_singleton = None
    _rate_limiters.clear()


def get_broker(settings: Settings = Depends(get_settings)) -> BrokerClient:
    global _broker_singleton
    if _broker_singleton is None:
        _broker_singleton = build_broker(settings)
    return _broker_singleton


def get_market_data(settings: Settings = Depends(get_settings)) -> MarketDataProvider:
    global _market_data_singleton
    if _market_data_singleton is None:
        if settings.market_data_provider == "alpaca":
            from app.services.market_data.alpaca_provider import AlpacaMarketDataProvider

            _market_data_singleton = AlpacaMarketDataProvider(settings)
        else:
            _market_data_singleton = MockMarketDataProvider()
    return _market_data_singleton


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    limiter = get_rate_limiter("global", settings.rate_limit_per_minute)
    if not limiter.allow(_client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded.")


async def auth_rate_limit(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    limiter = get_rate_limiter("auth", settings.auth_rate_limit_per_minute)
    if not limiter.allow(_client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts.")


def _session_payload(request: Request, settings: Settings) -> dict[str, Any]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    payload = verify_session_token(token, settings.app_secret_key.get_secret_value())
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalid or expired.")
    return payload


async def current_user(
    request: Request, settings: Settings = Depends(get_settings)
) -> str:
    payload = _session_payload(request, settings)
    return str(payload["sub"])


async def csrf_protect(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """Double-submit CSRF check for state-changing methods."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    payload = _session_payload(request, settings)
    header_token = request.headers.get("x-csrf-token", "")
    if not header_token or header_token != payload.get("csrf"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid.")
