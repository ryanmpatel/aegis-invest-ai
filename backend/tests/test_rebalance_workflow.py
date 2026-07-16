"""Integration tests for the full 25-step rebalance workflow."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.config import SchedulerConfig
from app.models.trading import (
    AccountSnapshot,
    ProposedTrade,
    RiskDecision,
    Signal,
    StrategyRun,
    TargetPortfolioRecord,
)
from app.models.trading import (
    Order as OrderModel,
)
from app.services.execution.locks import LocalLock
from app.services.execution.rebalance import RebalanceAborted, RebalanceWorkflow
from app.services.risk.kill_switch import set_kill_switch
from app.services.strategies.weekly_multi_factor import WeeklyMultiFactorTrendStrategy
from tests.conftest import seed_universe


def make_workflow(session, settings, mock_broker, market_data, **kwargs):
    return RebalanceWorkflow(
        session=session,
        settings=settings,
        broker=mock_broker,
        market_data=market_data,
        strategy=WeeklyMultiFactorTrendStrategy({"min_score": 0.0}),
        **kwargs,
    )


class TestPaperRebalance:
    async def test_full_rebalance_places_orders_and_records_everything(
        self, session, settings, mock_broker, market_data
    ):
        await seed_universe(session)
        # Align mock broker prices with the data provider's latest closes so
        # weights are internally consistent.
        for symbol in list(mock_broker.prices):
            trade = await market_data.get_latest_trade(symbol)
            if trade:
                mock_broker.set_price(symbol, trade.price)

        workflow = make_workflow(session, settings, mock_broker, market_data)
        result = await workflow.run(mode="paper", actor="test")
        assert result.status == "completed"
        assert result.submitted_orders > 0

        run = (
            await session.execute(select(StrategyRun).limit(1))
        ).scalar_one()
        assert run.status == "completed"

        signals = (await session.execute(select(Signal))).scalars().all()
        assert signals, "signals must be persisted"
        targets = (
            await session.execute(select(TargetPortfolioRecord))
        ).scalars().all()
        assert targets
        proposed = (await session.execute(select(ProposedTrade))).scalars().all()
        assert proposed
        decisions = (await session.execute(select(RiskDecision))).scalars().all()
        assert len(decisions) == len(proposed), "every proposed trade gets a decision"
        orders = (await session.execute(select(OrderModel))).scalars().all()
        assert orders
        for order in orders:
            assert order.risk_decision_id is not None, "order without risk approval!"
        snapshots = (await session.execute(select(AccountSnapshot))).scalars().all()
        assert len(snapshots) >= 2  # pre and post

        # Positions at the broker reconcile with local current rows.
        broker_positions = {p.symbol: p.quantity for p in await mock_broker.get_positions()}
        from app.models.trading import PositionRecord

        local = (
            await session.execute(
                select(PositionRecord).where(PositionRecord.is_current.is_(True))
            )
        ).scalars().all()
        local_map = {r.symbol: r.quantity for r in local}
        assert local_map == pytest.approx(broker_positions)

    async def test_preview_mode_submits_nothing(
        self, session, settings, mock_broker, market_data
    ):
        await seed_universe(session)
        workflow = make_workflow(session, settings, mock_broker, market_data)
        result = await workflow.run(mode="preview", actor="test")
        assert result.status == "completed"
        assert result.submitted_orders == 0
        assert len(mock_broker.orders) == 0
        decisions = (await session.execute(select(RiskDecision))).scalars().all()
        assert decisions, "preview still produces risk decisions"

    async def test_kill_switch_aborts_before_anything(
        self, session, settings, mock_broker, market_data
    ):
        await seed_universe(session)
        await set_kill_switch(session, active=True, actor="test", reason="drill")
        await session.commit()
        workflow = make_workflow(session, settings, mock_broker, market_data)
        with pytest.raises(RebalanceAborted, match="Kill switch"):
            await workflow.run(mode="paper", actor="test")
        assert len(mock_broker.orders) == 0

    async def test_frozen_trading_aborts(self, session, settings, mock_broker, market_data):
        await seed_universe(session)
        config = SchedulerConfig(trading_allowed=False, frozen_reason="test freeze")
        session.add(config)
        await session.commit()
        workflow = make_workflow(session, settings, mock_broker, market_data)
        with pytest.raises(RebalanceAborted, match="frozen"):
            await workflow.run(mode="paper", actor="test")

    async def test_broker_unreachable_freezes(
        self, session, settings, mock_broker, market_data
    ):
        await seed_universe(session)
        mock_broker.unreachable = True
        workflow = make_workflow(session, settings, mock_broker, market_data)
        with pytest.raises(RebalanceAborted, match="unreachable"):
            await workflow.run(mode="paper", actor="test")
        config = (
            await session.execute(select(SchedulerConfig).limit(1))
        ).scalar_one_or_none()
        assert config is not None and not config.trading_allowed

    async def test_missing_universe_aborts(
        self, session, settings, mock_broker, market_data
    ):
        workflow = make_workflow(session, settings, mock_broker, market_data)
        with pytest.raises(RebalanceAborted, match="universe"):
            await workflow.run(mode="paper", actor="test")

    async def test_duplicate_run_blocked_by_lock(
        self, session, settings, mock_broker, market_data
    ):
        await seed_universe(session)
        lock = LocalLock("rebalance")
        await lock.__aenter__()
        try:
            workflow = make_workflow(session, settings, mock_broker, market_data)
            with pytest.raises(RebalanceAborted, match="already in progress"):
                await workflow.run(mode="paper", actor="test")
        finally:
            await lock.__aexit__(None, None, None)

    async def test_second_run_after_first_makes_no_duplicate_orders(
        self, session, settings, mock_broker, market_data
    ):
        """Idempotent recovery: with capital-deployment caps lifted, run 1
        reaches target and an immediate rerun makes no meaningful new orders."""
        from app.models.config import RiskProfile
        from app.schemas.risk import RiskLimits

        await seed_universe(session)
        session.add(
            RiskProfile(
                name="test-full-deploy",
                is_active=True,
                limits=RiskLimits(
                    max_new_capital_per_rebalance_pct=0.95,
                    max_daily_turnover_pct=0.95,
                    max_order_notional=50_000.0,
                    max_position_pct=0.25,
                    max_position_notional=50_000.0,
                ).model_dump(),
            )
        )
        await session.commit()
        for symbol in list(mock_broker.prices):
            trade = await market_data.get_latest_trade(symbol)
            if trade:
                mock_broker.set_price(symbol, trade.price)
        workflow = make_workflow(session, settings, mock_broker, market_data)
        first = await workflow.run(mode="paper", actor="test")
        orders_after_first = len(mock_broker.orders)
        first_client_ids = set(mock_broker.client_index)
        assert first.submitted_orders > 0

        workflow2 = make_workflow(session, settings, mock_broker, market_data)
        await workflow2.run(mode="paper", actor="test")
        # Already at target: at most dust-level adjustments, and idempotency
        # keys never repeat across runs.
        assert len(mock_broker.orders) <= orders_after_first + 1
        assert first_client_ids <= set(mock_broker.client_index)
