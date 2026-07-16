"""Broker read endpoints and connection test. Read-only: order placement is
only reachable through the rebalance workflow, never directly via the API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import csrf_protect, current_user, get_broker
from app.services.broker.base import BrokerClient, BrokerUnavailableError

router = APIRouter(
    prefix="/api/broker",
    tags=["broker"],
    dependencies=[Depends(current_user)],
)


@router.get("/account")
async def account(broker: BrokerClient = Depends(get_broker)) -> dict:
    try:
        acct = await broker.get_account()
    except BrokerUnavailableError as exc:
        raise HTTPException(503, f"Broker unavailable: {exc}") from exc
    data = acct.model_dump()
    # Mask the account id — the frontend never needs the full value.
    if data.get("account_id"):
        data["account_id"] = data["account_id"][:2] + "…" + data["account_id"][-2:]
    return data


@router.get("/positions")
async def positions(broker: BrokerClient = Depends(get_broker)) -> list[dict]:
    try:
        return [p.model_dump() for p in await broker.get_positions()]
    except BrokerUnavailableError as exc:
        raise HTTPException(503, f"Broker unavailable: {exc}") from exc


@router.get("/orders")
async def open_orders(broker: BrokerClient = Depends(get_broker)) -> list[dict]:
    try:
        return [o.model_dump() for o in await broker.get_open_orders()]
    except BrokerUnavailableError as exc:
        raise HTTPException(503, f"Broker unavailable: {exc}") from exc


@router.post("/test-connection", dependencies=[Depends(csrf_protect)])
async def test_connection(broker: BrokerClient = Depends(get_broker)) -> dict:
    try:
        acct = await broker.get_account()
        clock = await broker.get_market_clock()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {
        "ok": True,
        "provider": broker.name,
        "is_paper": broker.is_paper,
        "equity": acct.equity,
        "market_open": clock.is_open,
    }
