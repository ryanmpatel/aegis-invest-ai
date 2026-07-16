"""Broker domain objects shared by mock and Alpaca adapters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(StrEnum):
    DAY = "day"


class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )


class Account(BaseModel):
    account_id: str
    equity: float
    cash: float
    buying_power: float
    long_market_value: float = 0.0
    currency: str = "USD"
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    is_paper: bool = True

    @field_validator("is_paper")
    @classmethod
    def _must_be_paper(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Live accounts are not supported. Paper trading only.")
        return v


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pl: float | None = None


class Order(BaseModel):
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    quantity: float
    filled_quantity: float = 0.0
    filled_avg_price: float | None = None
    status: OrderStatus = OrderStatus.NEW
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class ApprovedOrder(BaseModel):
    """The only object the execution engine will send to a broker.

    It must reference a risk-decision approval record; construction without
    one is impossible, which enforces the risk-review invariant in the type
    system as well as at runtime.
    """

    client_order_id: str = Field(min_length=8)
    risk_decision_id: str = Field(min_length=8)
    strategy_run_id: str = Field(min_length=8)
    symbol: str
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    reference_price: float = Field(gt=0)


class MarketClock(BaseModel):
    timestamp: datetime
    is_open: bool
    next_open: datetime | None = None
    next_close: datetime | None = None
