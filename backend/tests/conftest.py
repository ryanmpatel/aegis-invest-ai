"""Shared fixtures: in-memory database, settings, app client, mock providers.

The suite never touches external APIs; everything runs against mock providers
and SQLite.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-the-test-suite-only")
os.environ.setdefault("AUTH_USERNAME", "tester")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("BROKER_PROVIDER", "mock")
os.environ.setdefault("MARKET_DATA_PROVIDER", "mock")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.config import get_settings
from app.database import override_engine
from app.models import Base
from app.services.broker.mock_broker import MockBrokerClient
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.utils.security import hash_password

TEST_PASSWORD = "correct horse battery staple"
os.environ.setdefault("AUTH_PASSWORD_HASH", hash_password(TEST_PASSWORD))

DEFAULT_PRICES = {
    "SPY": 500.0, "QQQ": 430.0, "IWM": 210.0, "EFA": 78.0, "AGG": 98.0,
    "GLD": 215.0, "VNQ": 88.0, "XLE": 92.0, "TLT": 93.0, "DOWN": 40.0,
}


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    override_engine(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def mock_broker() -> MockBrokerClient:
    return MockBrokerClient(starting_cash=100_000.0, prices=dict(DEFAULT_PRICES))


@pytest.fixture
def market_data() -> MockMarketDataProvider:
    return MockMarketDataProvider()


@pytest.fixture
async def app(engine, settings, mock_broker, market_data):
    """FastAPI app wired to the test database and mock providers."""
    from app.api import deps
    from app.main import create_app

    deps.reset_singletons()
    application = create_app()
    application.dependency_overrides[deps.get_broker] = lambda: mock_broker
    application.dependency_overrides[deps.get_market_data] = lambda: market_data
    yield application
    deps.reset_singletons()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Client with a valid session cookie and CSRF header set."""
    response = await client.post(
        "/api/auth/login", json={"username": "tester", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    return client


async def seed_universe(session: AsyncSession, symbols: list[str] | None = None) -> None:
    from app.models.config import ApprovedUniverse

    session.add(
        ApprovedUniverse(
            name="default",
            symbols=symbols or ["SPY", "QQQ", "IWM", "EFA", "AGG", "GLD", "VNQ", "XLE"],
            is_active=True,
        )
    )
    await session.commit()
