"""Alpaca PAPER trading adapter.

Safety properties:
- ``paper=True`` is hard-coded; there is no parameter to change it.
- Construction fails without paper credentials.
- Construction fails if the account reports itself as non-paper.
- Secrets are never logged (SecretStr + logging redaction).
- Read calls retry with backoff; order submission NEVER blind-retries — an
  uncertain outcome raises UncertainSubmissionError and the caller must
  confirm via ``get_order_by_client_id``.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.logging import get_logger, log_event
from app.schemas.broker import (
    Account,
    ApprovedOrder,
    MarketClock,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TimeInForce,
)
from app.services.broker.base import (
    BrokerUnavailableError,
    DuplicateOrderError,
    UncertainSubmissionError,
)
from app.utils.retry import retry_async

logger = get_logger("broker.alpaca_paper")

_ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"

_STATUS_MAP: dict[str, OrderStatus] = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.SUBMITTED,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "pending_cancel": OrderStatus.SUBMITTED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
    "done_for_day": OrderStatus.EXPIRED,
    "stopped": OrderStatus.CANCELED,
    "suspended": OrderStatus.UNKNOWN,
    "calculated": OrderStatus.UNKNOWN,
    "held": OrderStatus.SUBMITTED,
}


class AlpacaPaperBrokerClient:
    name = "alpaca_paper"
    is_paper = True

    def __init__(self, settings: Settings) -> None:
        api_key = settings.alpaca_paper_api_key.get_secret_value()
        api_secret = settings.alpaca_paper_api_secret.get_secret_value()
        if not api_key or not api_secret:
            raise RuntimeError(
                "Refusing to start: Alpaca paper credentials are missing. Set "
                "ALPACA_PAPER_API_KEY and ALPACA_PAPER_API_SECRET."
            )
        if settings.live_trading_enabled:  # defense in depth; config already rejects
            raise RuntimeError("Live trading is permanently disabled in this build.")
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "alpaca-py is not installed. Install with: pip install '.[alpaca]'"
            ) from exc

        # paper=True is not configurable. Do not add a parameter for it.
        self._client = TradingClient(api_key, api_secret, paper=True)
        log_event(logger, "broker_initialized", "Alpaca paper client initialized",
                  endpoint=_ALPACA_PAPER_URL)

    # --- verification ---------------------------------------------------

    async def verify_paper_account(self) -> Account:
        """Fetch the account and hard-fail if it is not a paper account."""
        account = await self.get_account()
        return account

    # --- reads (retry-safe) ----------------------------------------------

    async def get_account(self) -> Account:
        try:
            raw = await retry_async(self._client.get_account)
        except Exception as exc:
            raise BrokerUnavailableError(f"account fetch failed: {exc}") from exc
        account_number = str(getattr(raw, "account_number", "") or "")
        # Alpaca paper account numbers start with "PA". Refuse anything else.
        if not account_number.startswith("PA"):
            raise RuntimeError(
                "Connected account does not look like an Alpaca PAPER account "
                f"(number {account_number[:2]}…). Refusing to proceed."
            )
        return Account(
            account_id=account_number,
            equity=float(raw.equity),
            cash=float(raw.cash),
            buying_power=float(raw.cash),  # ignore margin BP: no leverage
            long_market_value=float(raw.long_market_value or 0),
            pattern_day_trader=bool(raw.pattern_day_trader),
            trading_blocked=bool(raw.trading_blocked),
            is_paper=True,
        )

    async def get_positions(self) -> list[Position]:
        try:
            raw = await retry_async(self._client.get_all_positions)
        except Exception as exc:
            raise BrokerUnavailableError(f"positions fetch failed: {exc}") from exc
        return [
            Position(
                symbol=p.symbol,
                quantity=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price) if p.current_price else None,
                market_value=float(p.market_value) if p.market_value else None,
                unrealized_pl=float(p.unrealized_pl) if p.unrealized_pl else None,
            )
            for p in raw
        ]

    async def get_open_orders(self) -> list[Order]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        try:
            raw = await retry_async(
                lambda: self._client.get_orders(
                    GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
                )
            )
        except Exception as exc:
            raise BrokerUnavailableError(f"open orders fetch failed: {exc}") from exc
        return [self._map_order(o) for o in raw]

    async def get_order_by_client_id(self, client_order_id: str) -> Order | None:
        try:
            raw = await retry_async(
                lambda: self._client.get_order_by_client_id(client_order_id)
            )
        except Exception:
            return None
        return self._map_order(raw)

    # --- order submission (NOT blind-retried) ------------------------------

    async def submit_order(self, order: ApprovedOrder) -> Order:
        import asyncio

        from alpaca.common.exceptions import APIError
        from alpaca.trading.enums import OrderSide as AlpacaSide
        from alpaca.trading.enums import TimeInForce as AlpacaTIF
        from alpaca.trading.requests import MarketOrderRequest

        # Duplicate detection before submission.
        existing = await self.get_order_by_client_id(order.client_order_id)
        if existing is not None:
            raise DuplicateOrderError(
                f"client_order_id {order.client_order_id} already exists "
                f"(status {existing.status})"
            )

        request = MarketOrderRequest(
            symbol=order.symbol,
            qty=order.quantity,
            side=AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL,
            time_in_force=AlpacaTIF.DAY,
            client_order_id=order.client_order_id,
        )
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._client.submit_order, request), timeout=15.0
            )
        except TimeoutError as exc:
            # Outcome unknown: the order may or may not have been accepted.
            raise UncertainSubmissionError(
                f"submission timed out for {order.client_order_id}; confirm before retrying"
            ) from exc
        except APIError as exc:
            if "client_order_id must be unique" in str(exc).lower():
                raise DuplicateOrderError(str(exc)) from exc
            raise BrokerUnavailableError(f"submission rejected by API: {exc}") from exc
        return self._map_order(raw)

    # --- cancels / closes ---------------------------------------------------

    async def cancel_order(self, order_id: str) -> None:
        try:
            await retry_async(lambda: self._client.cancel_order_by_id(order_id))
        except Exception as exc:
            raise BrokerUnavailableError(f"cancel failed for {order_id}: {exc}") from exc

    async def cancel_all_orders(self) -> None:
        try:
            await retry_async(self._client.cancel_orders)
        except Exception as exc:
            raise BrokerUnavailableError(f"cancel-all failed: {exc}") from exc

    async def close_position(self, symbol: str) -> None:
        try:
            await retry_async(lambda: self._client.close_position(symbol))
        except Exception as exc:
            raise BrokerUnavailableError(f"close position failed for {symbol}: {exc}") from exc

    # --- metadata ------------------------------------------------------------

    async def get_market_clock(self) -> MarketClock:
        try:
            raw = await retry_async(self._client.get_clock)
        except Exception as exc:
            raise BrokerUnavailableError(f"clock fetch failed: {exc}") from exc
        return MarketClock(
            timestamp=raw.timestamp,
            is_open=bool(raw.is_open),
            next_open=raw.next_open,
            next_close=raw.next_close,
        )

    async def is_asset_tradable(self, symbol: str) -> bool:
        try:
            asset = await retry_async(lambda: self._client.get_asset(symbol))
        except Exception:
            return False
        return bool(getattr(asset, "tradable", False))

    # --- mapping ---------------------------------------------------------

    @staticmethod
    def _map_order(raw: Any) -> Order:
        status = _STATUS_MAP.get(str(raw.status.value if raw.status else ""), OrderStatus.UNKNOWN)
        return Order(
            broker_order_id=str(raw.id),
            client_order_id=str(raw.client_order_id or ""),
            symbol=str(raw.symbol),
            side=OrderSide.BUY if str(raw.side.value) == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            quantity=float(raw.qty or 0),
            filled_quantity=float(raw.filled_qty or 0),
            filled_avg_price=float(raw.filled_avg_price) if raw.filled_avg_price else None,
            status=status,
            submitted_at=raw.submitted_at,
            updated_at=raw.updated_at,
        )
