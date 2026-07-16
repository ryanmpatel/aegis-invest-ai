"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import rate_limit
from app.api.router import api_router
from app.config import get_settings
from app.database import dispose_engine, get_engine
from app.logging import configure_logging, get_logger, log_event
from app.models import Base
from app.workers.scheduler import shutdown_scheduler, start_scheduler

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    if settings.live_trading_enabled:  # config validation already rejects this
        raise RuntimeError("Live trading is permanently disabled in this build.")
    if settings.app_env != "production":
        # Dev/test convenience: create tables when migrations haven't run.
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    start_scheduler(settings)
    log_event(
        logger, "startup",
        f"AegisInvest AI backend started (env={settings.app_env}, "
        f"broker={settings.broker_provider}, paper-only)",
    )
    yield
    shutdown_scheduler()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AegisInvest AI",
        description=(
            "Automated investing research, backtesting and PAPER-trading platform. "
            "Educational software: nothing here is investment advice, and no "
            "strategy is guaranteed to be profitable. Live trading is disabled."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def apply_rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api"):
            try:
                await rate_limit(request, get_settings())
            except Exception:
                return JSONResponse(
                    status_code=429, content={"detail": "Rate limit exceeded."}
                )
        return await call_next(request)

    @app.exception_handler(Exception)
    async def safe_error_handler(request: Request, exc: Exception):
        # Never leak internals or secrets in error responses.
        log_event(logger, "unhandled_error", f"{exc.__class__.__name__} on "
                  f"{request.url.path}", severity=40)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )

    app.include_router(api_router)
    return app


app = create_app()
