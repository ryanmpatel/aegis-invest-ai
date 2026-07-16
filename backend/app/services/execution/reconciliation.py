"""Reconciliation between local records and broker state.

A mismatch is a freeze condition: trading must not proceed on state we cannot
trust.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.trading import Order as OrderModel
from app.models.trading import PositionRecord, ReconciliationReport
from app.services.broker.base import BrokerClient
from app.utils.timeutils import utcnow

logger = get_logger("execution.reconciliation")

_QTY_TOLERANCE = 1e-6


async def reconcile(
    session: AsyncSession, broker: BrokerClient, correlation_id: str = ""
) -> ReconciliationReport:
    discrepancies: list[dict] = []

    # --- positions -------------------------------------------------------
    broker_positions = {p.symbol: p for p in await broker.get_positions()}
    local_rows = (
        await session.execute(
            select(PositionRecord).where(PositionRecord.is_current.is_(True))
        )
    ).scalars().all()
    local_positions = {r.symbol: r for r in local_rows}

    for symbol, broker_pos in broker_positions.items():
        local = local_positions.get(symbol)
        if local is None:
            discrepancies.append({
                "type": "position_missing_locally", "symbol": symbol,
                "broker_quantity": broker_pos.quantity,
            })
        elif abs(local.quantity - broker_pos.quantity) > _QTY_TOLERANCE:
            discrepancies.append({
                "type": "position_quantity_mismatch", "symbol": symbol,
                "local_quantity": local.quantity,
                "broker_quantity": broker_pos.quantity,
            })
    for symbol, local in local_positions.items():
        if symbol not in broker_positions and local.quantity > _QTY_TOLERANCE:
            discrepancies.append({
                "type": "position_missing_at_broker", "symbol": symbol,
                "local_quantity": local.quantity,
            })

    # --- open orders -------------------------------------------------------
    broker_open = {o.client_order_id: o for o in await broker.get_open_orders()}
    local_open_rows = (
        await session.execute(
            select(OrderModel).where(
                OrderModel.status.in_(["new", "submitted", "partially_filled", "unknown"])
            )
        )
    ).scalars().all()
    for row in local_open_rows:
        if row.status == "unknown":
            discrepancies.append({
                "type": "order_status_unknown",
                "client_order_id": row.client_order_id, "symbol": row.symbol,
            })
            continue
        if row.client_order_id not in broker_open and row.status != "new":
            # Locally open but broker no longer lists it: refresh from broker.
            broker_order = await broker.get_order_by_client_id(row.client_order_id)
            if broker_order is None:
                discrepancies.append({
                    "type": "order_missing_at_broker",
                    "client_order_id": row.client_order_id, "symbol": row.symbol,
                })
            else:
                row.status = broker_order.status.value
                row.filled_quantity = broker_order.filled_quantity
                row.filled_avg_price = broker_order.filled_avg_price
                if broker_order.status.is_terminal:
                    row.closed_at = utcnow()
    for client_id, broker_order in broker_open.items():
        if client_id and not any(r.client_order_id == client_id for r in local_open_rows):
            discrepancies.append({
                "type": "order_unknown_locally", "client_order_id": client_id,
                "symbol": broker_order.symbol,
            })

    report = ReconciliationReport(
        correlation_id=correlation_id,
        matched=not discrepancies,
        discrepancies=discrepancies,
    )
    session.add(report)
    await session.flush()
    log_event(
        logger, "reconciliation",
        "reconciliation matched" if report.matched
        else f"reconciliation found {len(discrepancies)} discrepancies",
        matched=report.matched, discrepancy_count=len(discrepancies),
    )
    return report


async def sync_positions_from_broker(
    session: AsyncSession, broker: BrokerClient
) -> None:
    """Replace current local position rows with broker truth (append-style:
    old rows are marked not-current, new rows inserted)."""
    now = utcnow()
    old_rows = (
        await session.execute(
            select(PositionRecord).where(PositionRecord.is_current.is_(True))
        )
    ).scalars().all()
    for row in old_rows:
        row.is_current = False
    for pos in await broker.get_positions():
        session.add(
            PositionRecord(
                symbol=pos.symbol,
                quantity=pos.quantity,
                avg_entry_price=pos.avg_entry_price,
                current_price=pos.current_price,
                market_value=pos.market_value,
                unrealized_pl=pos.unrealized_pl,
                as_of=now,
                is_current=True,
            )
        )
    await session.flush()
