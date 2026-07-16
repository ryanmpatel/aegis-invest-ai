"""In-memory mock broker for development and tests.

Simulates: immediate/partial fills, rejections, duplicate detection,
timeouts with uncertain outcomes, and a market clock. Deterministic unless
failure modes are explicitly injected.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, time, timedelta

from app.schemas.broker import (
    Account,
    ApprovedOrder,
    MarketClock,
    Order,
    OrderStatus,
    Position,
)
from app.services.broker.base import (
    BrokerUnavailableError,
    DuplicateOrderError,
    UncertainSubmissionError,
)


class MockBrokerClient:
    name = "mock"
    is_paper = True

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        prices: dict[str, float] | None = None,
        tradable: set[str] | None = None,
    ) -> None:
        self.cash = starting_cash
        self.prices = dict(prices or {})
        self.tradable_symbols = set(tradable) if tradable is not None else set(self.prices)
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, Order] = {}          # broker_order_id -> Order
        self.client_index: dict[str, str] = {}       # client_order_id -> broker_order_id
        self._id_counter = itertools.count(1)
        # Failure injection knobs (tests set these)
        self.fail_next_submission: str | None = None  # "reject"|"timeout"|"unavailable"|"partial"
        self.unreachable = False
        self.market_open = True

    # ------------------------------------------------------------------

    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol] = price
        for pos in self.positions.values():
            if pos.symbol == symbol:
                pos.current_price = price
                pos.market_value = pos.quantity * price
                pos.unrealized_pl = (price - pos.avg_entry_price) * pos.quantity

    def _require_reachable(self) -> None:
        if self.unreachable:
            raise BrokerUnavailableError("mock broker is unreachable")

    # ------------------------------------------------------------------

    async def get_account(self) -> Account:
        self._require_reachable()
        long_value = sum(
            (p.market_value or p.quantity * self.prices.get(p.symbol, p.avg_entry_price))
            for p in self.positions.values()
        )
        return Account(
            account_id="MOCK-PAPER-0001",
            equity=self.cash + long_value,
            cash=self.cash,
            buying_power=self.cash,  # no leverage, ever
            long_market_value=long_value,
            is_paper=True,
        )

    async def get_positions(self) -> list[Position]:
        self._require_reachable()
        return [p.model_copy() for p in self.positions.values() if p.quantity > 0]

    async def get_open_orders(self) -> list[Order]:
        self._require_reachable()
        return [
            o.model_copy() for o in self.orders.values() if not o.status.is_terminal
        ]

    async def get_order_by_client_id(self, client_order_id: str) -> Order | None:
        self._require_reachable()
        broker_id = self.client_index.get(client_order_id)
        return self.orders[broker_id].model_copy() if broker_id else None

    async def submit_order(self, order: ApprovedOrder) -> Order:
        self._require_reachable()
        if order.client_order_id in self.client_index:
            raise DuplicateOrderError(
                f"client_order_id {order.client_order_id} already submitted"
            )

        failure, self.fail_next_submission = self.fail_next_submission, None
        if failure == "unavailable":
            raise BrokerUnavailableError("mock submission connectivity failure")

        broker_id = f"mock-order-{next(self._id_counter)}"
        now = datetime.now(UTC)
        record = Order(
            broker_order_id=broker_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            time_in_force=order.time_in_force,
            quantity=order.quantity,
            status=OrderStatus.SUBMITTED,
            submitted_at=now,
            updated_at=now,
        )
        self.orders[broker_id] = record
        self.client_index[order.client_order_id] = broker_id

        if failure == "timeout":
            # Order WAS accepted but the caller never learns the result.
            self._fill(record, order.quantity)
            raise UncertainSubmissionError("mock submission timed out after send")
        if failure == "reject":
            record.status = OrderStatus.REJECTED
            record.updated_at = datetime.now(UTC)
            return record.model_copy()
        if failure == "partial":
            self._fill(record, order.quantity / 2, partial=True)
            return record.model_copy()

        self._fill(record, order.quantity)
        return record.model_copy()

    def _fill(self, record: Order, quantity: float, partial: bool = False) -> None:
        price = self.prices.get(record.symbol)
        if price is None or price <= 0:
            record.status = OrderStatus.REJECTED
            return
        if record.side == "sell":
            held = self.positions.get(record.symbol)
            available = held.quantity if held else 0.0
            quantity = min(quantity, available)
            if quantity <= 0:
                record.status = OrderStatus.REJECTED
                return
        record.filled_quantity = quantity
        record.filled_avg_price = price
        record.status = OrderStatus.PARTIALLY_FILLED if partial else OrderStatus.FILLED
        record.updated_at = datetime.now(UTC)

        if record.side == "buy":
            cost = quantity * price
            self.cash -= cost
            pos = self.positions.get(record.symbol)
            if pos is None:
                self.positions[record.symbol] = Position(
                    symbol=record.symbol, quantity=quantity, avg_entry_price=price,
                    current_price=price, market_value=quantity * price, unrealized_pl=0.0,
                )
            else:
                total_qty = pos.quantity + quantity
                pos.avg_entry_price = (
                    pos.avg_entry_price * pos.quantity + price * quantity
                ) / total_qty
                pos.quantity = total_qty
                pos.market_value = total_qty * price
        else:
            pos = self.positions[record.symbol]
            pos.quantity -= quantity
            self.cash += quantity * price
            if pos.quantity <= 1e-9:
                del self.positions[record.symbol]
            else:
                pos.market_value = pos.quantity * price

    async def cancel_order(self, order_id: str) -> None:
        self._require_reachable()
        order = self.orders.get(order_id)
        if order and not order.status.is_terminal:
            order.status = OrderStatus.CANCELED
            order.updated_at = datetime.now(UTC)

    async def cancel_all_orders(self) -> None:
        self._require_reachable()
        for order in self.orders.values():
            if not order.status.is_terminal:
                order.status = OrderStatus.CANCELED
                order.updated_at = datetime.now(UTC)

    async def close_position(self, symbol: str) -> None:
        self._require_reachable()
        pos = self.positions.get(symbol)
        if pos is None:
            return
        price = self.prices.get(symbol, pos.avg_entry_price)
        self.cash += pos.quantity * price
        del self.positions[symbol]

    async def get_market_clock(self) -> MarketClock:
        self._require_reachable()
        now = datetime.now(UTC)
        return MarketClock(
            timestamp=now,
            is_open=self.market_open,
            next_open=datetime.combine(now.date() + timedelta(days=1), time(14, 30), UTC),
            next_close=datetime.combine(now.date(), time(21, 0), UTC),
        )

    async def is_asset_tradable(self, symbol: str) -> bool:
        self._require_reachable()
        return symbol in self.tradable_symbols
