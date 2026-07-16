"""Execution engine — the ONLY component that talks to the broker.

Invariants enforced here:
- Orders require an ApprovedOrder (which requires a risk-decision id).
- Kill switch active → no submission, period.
- Idempotency: client_order_id is deterministic per (run, symbol, side);
  duplicates are detected locally and at the broker.
- Uncertain submissions are confirmed before any retry.
- The full order lifecycle is recorded append-only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.trading import Fill, OrderEvent
from app.models.trading import Order as OrderModel
from app.schemas.broker import ApprovedOrder, Order, OrderStatus
from app.services.broker.base import (
    BrokerClient,
    DuplicateOrderError,
    UncertainSubmissionError,
)
from app.services.risk.kill_switch import is_kill_switch_active
from app.utils.timeutils import utcnow

logger = get_logger("execution.engine")


class KillSwitchActiveError(Exception):
    pass


class ExecutionEngine:
    def __init__(self, broker: BrokerClient, session: AsyncSession) -> None:
        if not broker.is_paper:
            raise RuntimeError("Execution engine refuses non-paper broker clients.")
        self.broker = broker
        self.session = session

    async def _record_event(self, order_row: OrderModel, event_type: str, payload: dict) -> None:
        self.session.add(
            OrderEvent(order_id=order_row.id, event_type=event_type, payload=payload)
        )
        await self.session.flush()

    async def _find_local_order(self, client_order_id: str) -> OrderModel | None:
        return (
            await self.session.execute(
                select(OrderModel).where(OrderModel.client_order_id == client_order_id)
            )
        ).scalar_one_or_none()

    async def submit(self, approved: ApprovedOrder) -> OrderModel:
        """Submit an approved order idempotently and record its lifecycle."""
        if await is_kill_switch_active(self.session):
            raise KillSwitchActiveError("Kill switch active — order submission blocked.")

        # Local duplicate detection (same idempotency key already processed).
        existing = await self._find_local_order(approved.client_order_id)
        if existing is not None and existing.status not in ("new", "unknown"):
            log_event(
                logger, "duplicate_submission_blocked",
                f"Duplicate submission blocked for {approved.client_order_id}",
                symbol=approved.symbol, client_order_id=approved.client_order_id,
            )
            return existing

        # Validate tradability immediately before submission.
        if not await self.broker.is_asset_tradable(approved.symbol):
            raise ValueError(f"{approved.symbol} is not tradable at the broker.")

        order_row = existing or OrderModel(
            strategy_run_id=uuid.UUID(approved.strategy_run_id),
            risk_decision_id=uuid.UUID(approved.risk_decision_id),
            client_order_id=approved.client_order_id,
            symbol=approved.symbol,
            side=approved.side.value,
            order_type=approved.order_type.value,
            time_in_force=approved.time_in_force.value,
            quantity=approved.quantity,
            status="new",
        )
        if existing is None:
            self.session.add(order_row)
            await self.session.flush()
        await self._record_event(order_row, "submission_attempt", {
            "symbol": approved.symbol, "side": approved.side.value,
            "quantity": approved.quantity,
        })

        try:
            broker_order = await self.broker.submit_order(approved)
        except UncertainSubmissionError:
            # Do NOT retry blindly. Mark unknown, then confirm.
            order_row.status = "unknown"
            await self._record_event(order_row, "submission_uncertain", {})
            confirmed = await self.broker.get_order_by_client_id(approved.client_order_id)
            if confirmed is None:
                # Confirmed not received: safe to leave as failed-unknown; a
                # future run may resubmit under a new decision.
                order_row.status = "rejected"
                order_row.closed_at = utcnow()
                await self._record_event(order_row, "submission_confirmed_absent", {})
                await self.session.flush()
                return order_row
            broker_order = confirmed
            await self._record_event(order_row, "submission_confirmed_present", {
                "broker_order_id": broker_order.broker_order_id,
            })
        except DuplicateOrderError:
            confirmed = await self.broker.get_order_by_client_id(approved.client_order_id)
            if confirmed is None:
                raise
            broker_order = confirmed
            await self._record_event(order_row, "duplicate_confirmed", {
                "broker_order_id": broker_order.broker_order_id,
            })

        await self._apply_broker_state(order_row, broker_order)
        return order_row

    async def _apply_broker_state(self, order_row: OrderModel, broker_order: Order) -> None:
        order_row.broker_order_id = broker_order.broker_order_id
        order_row.status = broker_order.status.value
        order_row.filled_quantity = broker_order.filled_quantity
        order_row.filled_avg_price = broker_order.filled_avg_price
        order_row.submitted_at = broker_order.submitted_at or utcnow()
        if broker_order.status.is_terminal:
            order_row.closed_at = utcnow()
        await self._record_event(order_row, "broker_state", {
            "status": broker_order.status.value,
            "filled_quantity": broker_order.filled_quantity,
            "filled_avg_price": broker_order.filled_avg_price,
        })
        if (
            broker_order.filled_quantity > 0
            and broker_order.filled_avg_price is not None
        ):
            existing_fill = (
                await self.session.execute(
                    select(Fill).where(Fill.order_id == order_row.id)
                )
            ).scalars().first()
            if existing_fill is None:
                self.session.add(
                    Fill(
                        order_id=order_row.id,
                        symbol=order_row.symbol,
                        side=order_row.side,
                        quantity=broker_order.filled_quantity,
                        price=broker_order.filled_avg_price,
                        filled_at=utcnow(),
                    )
                )
        await self.session.flush()
        log_event(
            logger, "order_state", f"{order_row.symbol} {order_row.side} → {order_row.status}",
            symbol=order_row.symbol, order_status=order_row.status,
            client_order_id=order_row.client_order_id,
        )

    async def refresh_order(self, order_row: OrderModel) -> OrderModel:
        """Poll the broker for the current state of a local order."""
        broker_order = await self.broker.get_order_by_client_id(order_row.client_order_id)
        if broker_order is not None:
            await self._apply_broker_state(order_row, broker_order)
        return order_row

    async def cancel_open_buy_orders(self) -> int:
        """Cancel open buy orders (kill-switch / limit-breach response)."""
        open_orders = await self.broker.get_open_orders()
        canceled = 0
        for order in open_orders:
            if order.side == "buy":
                await self.broker.cancel_order(order.broker_order_id)
                canceled += 1
                local = await self._find_local_order(order.client_order_id)
                if local is not None:
                    local.status = OrderStatus.CANCELED.value
                    local.closed_at = utcnow()
                    await self._record_event(local, "canceled_by_safety", {})
        await self.session.flush()
        return canceled
