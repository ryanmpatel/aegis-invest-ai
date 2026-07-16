"""Execution-engine tests: idempotency, duplicates, uncertain submissions,
kill switch, partial fills, broker failure."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.trading import Fill, OrderEvent
from app.models.trading import Order as OrderModel
from app.schemas.broker import ApprovedOrder, OrderSide
from app.services.broker.base import BrokerUnavailableError
from app.services.execution.engine import ExecutionEngine, KillSwitchActiveError
from app.services.risk.kill_switch import set_kill_switch
from app.utils.ids import idempotency_key

RUN_ID = str(uuid.uuid4())
DECISION_ID = str(uuid.uuid4())


def approved(symbol="SPY", side=OrderSide.BUY, quantity=10.0, seq=0) -> ApprovedOrder:
    return ApprovedOrder(
        client_order_id=idempotency_key(RUN_ID, symbol, side.value, seq),
        risk_decision_id=DECISION_ID,
        strategy_run_id=RUN_ID,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=500.0,
    )


class TestSubmission:
    async def test_successful_buy_records_lifecycle(self, session, mock_broker):
        engine = ExecutionEngine(mock_broker, session)
        row = await engine.submit(approved())
        assert row.status == "filled"
        assert row.broker_order_id
        events = (
            await session.execute(select(OrderEvent).where(OrderEvent.order_id == row.id))
        ).scalars().all()
        types = [e.event_type for e in events]
        assert "submission_attempt" in types
        assert "broker_state" in types
        fills = (
            await session.execute(select(Fill).where(Fill.order_id == row.id))
        ).scalars().all()
        assert len(fills) == 1
        assert fills[0].quantity == pytest.approx(10)

    async def test_idempotent_resubmission_returns_existing(self, session, mock_broker):
        engine = ExecutionEngine(mock_broker, session)
        first = await engine.submit(approved(seq=1))
        second = await engine.submit(approved(seq=1))
        assert first.id == second.id
        orders = (
            await session.execute(
                select(OrderModel).where(
                    OrderModel.client_order_id == approved(seq=1).client_order_id
                )
            )
        ).scalars().all()
        assert len(orders) == 1
        # Broker saw exactly one order too.
        assert len(mock_broker.orders) == 1

    async def test_duplicate_scheduler_runs_do_not_duplicate_orders(
        self, session, mock_broker
    ):
        """Same run/symbol/side/seq → same idempotency key → one order."""
        engine = ExecutionEngine(mock_broker, session)
        await engine.submit(approved(seq=2))
        await engine.submit(approved(seq=2))
        await engine.submit(approved(seq=2))
        assert len(mock_broker.orders) == 1

    async def test_rejected_order_recorded(self, session, mock_broker):
        mock_broker.fail_next_submission = "reject"
        engine = ExecutionEngine(mock_broker, session)
        row = await engine.submit(approved(seq=3))
        assert row.status == "rejected"

    async def test_partial_fill_recorded(self, session, mock_broker):
        mock_broker.fail_next_submission = "partial"
        engine = ExecutionEngine(mock_broker, session)
        row = await engine.submit(approved(seq=4))
        assert row.status == "partially_filled"
        assert row.filled_quantity == pytest.approx(5)

    async def test_uncertain_submission_confirmed_not_retried(
        self, session, mock_broker
    ):
        """Timeout after send → confirm via client id; never a second order."""
        mock_broker.fail_next_submission = "timeout"
        engine = ExecutionEngine(mock_broker, session)
        row = await engine.submit(approved(seq=5))
        assert row.status == "filled"  # confirmed the order actually went through
        assert len(mock_broker.orders) == 1
        events = (
            await session.execute(select(OrderEvent).where(OrderEvent.order_id == row.id))
        ).scalars().all()
        assert any(e.event_type == "submission_uncertain" for e in events)
        assert any(e.event_type == "submission_confirmed_present" for e in events)

    async def test_network_failure_before_send_raises(self, session, mock_broker):
        mock_broker.fail_next_submission = "unavailable"
        engine = ExecutionEngine(mock_broker, session)
        with pytest.raises(BrokerUnavailableError):
            await engine.submit(approved(seq=6))
        # Nothing reached the broker.
        assert len(mock_broker.orders) == 0

    async def test_non_tradable_symbol_refused(self, session, mock_broker):
        mock_broker.tradable_symbols.discard("SPY")
        engine = ExecutionEngine(mock_broker, session)
        with pytest.raises(ValueError, match="not tradable"):
            await engine.submit(approved(seq=7))


class TestKillSwitch:
    async def test_kill_switch_blocks_submission(self, session, mock_broker):
        await set_kill_switch(session, active=True, actor="test", reason="drill")
        engine = ExecutionEngine(mock_broker, session)
        with pytest.raises(KillSwitchActiveError):
            await engine.submit(approved(seq=8))
        assert len(mock_broker.orders) == 0

    async def test_kill_switch_deactivation_restores(self, session, mock_broker):
        await set_kill_switch(session, active=True, actor="test", reason="drill")
        await set_kill_switch(session, active=False, actor="test", reason="drill over")
        engine = ExecutionEngine(mock_broker, session)
        row = await engine.submit(approved(seq=9))
        assert row.status == "filled"

    async def test_cancel_open_buy_orders(self, session, mock_broker):
        from app.schemas.broker import Order, OrderStatus

        # Seed an open buy order directly into the mock broker.
        mock_broker.orders["mock-1"] = Order(
            broker_order_id="mock-1", client_order_id="c-1", symbol="SPY",
            side=OrderSide.BUY, quantity=5, status=OrderStatus.SUBMITTED,
        )
        mock_broker.client_index["c-1"] = "mock-1"
        engine = ExecutionEngine(mock_broker, session)
        canceled = await engine.cancel_open_buy_orders()
        assert canceled == 1
        assert mock_broker.orders["mock-1"].status == OrderStatus.CANCELED


class TestPaperOnlyGuard:
    async def test_non_paper_broker_rejected(self, session, mock_broker):
        mock_broker.is_paper = False
        with pytest.raises(RuntimeError, match="paper"):
            ExecutionEngine(mock_broker, session)
