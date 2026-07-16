"""Broker client protocol.

Only the execution engine may hold a BrokerClient. ``submit_order`` accepts
only ``ApprovedOrder`` — an object that cannot exist without a risk-decision
record — so a strategy or AI provider cannot construct a valid submission.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.broker import Account, ApprovedOrder, MarketClock, Order, Position


class BrokerError(Exception):
    """Base class for broker failures."""


class BrokerUnavailableError(BrokerError):
    """Connectivity/timeout failures where the request state is KNOWN not applied."""


class UncertainSubmissionError(BrokerError):
    """The submission outcome is unknown (e.g. timeout after send).

    Callers must confirm via ``get_order_by_client_id`` before any retry."""


class DuplicateOrderError(BrokerError):
    """An order with the same client_order_id already exists."""


@runtime_checkable
class BrokerClient(Protocol):
    name: str
    is_paper: bool

    async def get_account(self) -> Account: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_open_orders(self) -> list[Order]: ...
    async def get_order_by_client_id(self, client_order_id: str) -> Order | None: ...
    async def submit_order(self, order: ApprovedOrder) -> Order: ...
    async def cancel_order(self, order_id: str) -> None: ...
    async def cancel_all_orders(self) -> None: ...
    async def close_position(self, symbol: str) -> None: ...
    async def get_market_clock(self) -> MarketClock: ...
    async def is_asset_tradable(self, symbol: str) -> bool: ...
