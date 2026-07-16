"""Aggregate API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    auth,
    backtests,
    broker,
    dashboard,
    health,
    paper_trading,
    risk,
    settings_api,
    strategies,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(broker.router)
api_router.include_router(strategies.router)
api_router.include_router(backtests.router)
api_router.include_router(paper_trading.router)
api_router.include_router(risk.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings_api.router)
