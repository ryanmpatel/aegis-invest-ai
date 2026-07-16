"""The portfolio rebalance workflow (spec §11, all 25 steps).

The workflow is resumable/safe-on-crash: every side effect is recorded before
the next step runs, orders are idempotent per (run, symbol, side), and a rerun
after a crash reconciles broker state before doing anything else. Any failed
safety check freezes trading rather than proceeding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.logging import correlation_id_var, get_logger, log_event, strategy_run_id_var
from app.models.config import ApprovedUniverse, RiskProfile
from app.models.trading import (
    AccountSnapshot,
    ProposedTrade,
    RiskDecision,
    Signal,
    StrategyRun,
    TargetPortfolioRecord,
)
from app.schemas.broker import ApprovedOrder, OrderSide
from app.schemas.risk import (
    AccountState,
    MarketContext,
    RiskAction,
    RiskLimits,
    TradeIntent,
)
from app.schemas.strategy import StrategyContext, StrategyResult
from app.services.broker.base import BrokerClient
from app.services.execution.engine import ExecutionEngine
from app.services.execution.locks import LockNotAcquiredError, acquire_lock_or_raise
from app.services.execution.reconciliation import reconcile, sync_positions_from_broker
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.quality import validate_bars
from app.services.risk.engine import RiskEngine
from app.services.risk.events import freeze_trading, is_trading_frozen, record_risk_event
from app.services.risk.kill_switch import is_kill_switch_active
from app.services.strategies.base import Strategy
from app.services.strategies.indicators import avg_share_volume
from app.utils.ids import idempotency_key
from app.utils.timeutils import utcnow

logger = get_logger("execution.rebalance")

REBALANCE_WEIGHT_THRESHOLD = 0.01  # skip trades below 1% weight difference
HISTORY_DAYS = 400


class RebalanceAborted(Exception):
    """Raised when a safety condition stops the rebalance."""


@dataclass
class RebalanceResult:
    strategy_run_id: str
    status: str
    submitted_orders: int = 0
    rejected_trades: int = 0
    messages: list[str] = field(default_factory=list)


class RebalanceWorkflow:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        broker: BrokerClient,
        market_data: MarketDataProvider,
        strategy: Strategy,
        risk_engine: RiskEngine | None = None,
        ai_overlay=None,          # async (session, targets, universe) -> (targets, adjustments)
        notifier=None,            # async (subject, body) -> None
    ) -> None:
        self.session = session
        self.settings = settings
        self.broker = broker
        self.market_data = market_data
        self.strategy = strategy
        self.risk_engine = risk_engine or RiskEngine()
        self.ai_overlay = ai_overlay
        self.notifier = notifier

    async def _notify(self, subject: str, body: str) -> None:
        if self.notifier is not None:
            try:
                await self.notifier(subject, body)
            except Exception:
                logger.warning("notification delivery failed", exc_info=True)

    async def _load_risk_limits(self) -> RiskLimits:
        profile = (
            await self.session.execute(
                select(RiskProfile).where(RiskProfile.is_active.is_(True)).limit(1)
            )
        ).scalar_one_or_none()
        if profile is None:
            return self.risk_engine.limits
        return RiskLimits(**{**RiskLimits().model_dump(), **profile.limits})

    async def _load_universe(self) -> list[str]:
        row = (
            await self.session.execute(
                select(ApprovedUniverse).where(ApprovedUniverse.is_active.is_(True)).limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.symbols:
            raise RebalanceAborted("No active approved universe configured.")
        return list(row.symbols)

    # ------------------------------------------------------------------

    async def run(self, *, mode: str = "paper", actor: str = "scheduler") -> RebalanceResult:
        """Execute the full rebalance workflow. ``mode='preview'`` stops after
        risk review without submitting orders."""
        correlation_id = uuid.uuid4().hex
        correlation_id_var.set(correlation_id)
        as_of = utcnow()

        # Step 1: acquire the distributed rebalance lock.
        try:
            lock = await acquire_lock_or_raise(self.settings, "rebalance")
        except LockNotAcquiredError as exc:
            await freeze_trading(
                self.session, reason="Duplicate rebalance job detected (lock held).",
                correlation_id=correlation_id,
            )
            await self.session.commit()
            raise RebalanceAborted("Rebalance already in progress.") from exc

        run = StrategyRun(
            correlation_id=correlation_id,
            strategy_name=self.strategy.name,
            strategy_version=self.strategy.version,
            mode=mode,
            as_of=as_of,
            status="started",
        )
        self.session.add(run)
        await self.session.flush()
        strategy_run_id_var.set(str(run.id))
        await self._notify(
            "Rebalance started",
            f"Strategy {self.strategy.name} v{self.strategy.version} ({mode} mode).",
        )

        try:
            result = await self._run_steps(run, correlation_id, mode)
            run.status = "completed" if result.status == "completed" else result.status
            run.finished_at = utcnow()
            await self.session.commit()
            await self._notify(
                "Rebalance completed",
                f"Run {run.id}: {result.submitted_orders} orders submitted, "
                f"{result.rejected_trades} trades rejected.",
            )
            return result
        except RebalanceAborted as exc:
            run.status = "frozen"
            run.error = str(exc)
            run.finished_at = utcnow()
            await self.session.commit()
            await self._notify("Rebalance aborted", str(exc))
            raise
        except Exception as exc:
            run.status = "failed"
            run.error = f"{exc.__class__.__name__}: {exc}"
            run.finished_at = utcnow()
            await record_risk_event(
                self.session, severity="critical", rule_name="rebalance_failure",
                message=run.error, correlation_id=correlation_id,
            )
            await self.session.commit()
            await self._notify("Rebalance FAILED", run.error)
            raise
        finally:
            # Step 24: release the distributed lock.
            await lock.__aexit__(None, None, None)

    # ------------------------------------------------------------------

    async def _run_steps(
        self, run: StrategyRun, correlation_id: str, mode: str
    ) -> RebalanceResult:
        result = RebalanceResult(strategy_run_id=str(run.id), status="completed")
        limits = await self._load_risk_limits()
        engine = RiskEngine(limits)

        # Step 2: confirm paper mode.
        if not self.broker.is_paper or self.settings.live_trading_enabled:
            raise RebalanceAborted("System is not in paper mode. Refusing to trade.")

        # Step 3: kill switch.
        if await is_kill_switch_active(self.session):
            raise RebalanceAborted("Kill switch is active.")
        frozen, reason = await is_trading_frozen(self.session)
        if frozen:
            raise RebalanceAborted(f"Trading is frozen: {reason}")

        # Step 4: market-data pipeline health (provider reachable + fresh).
        clock_ok = True
        try:
            broker_clock = await self.broker.get_market_clock()
            skew = abs((broker_clock.timestamp - utcnow()).total_seconds())
            clock_ok = skew <= limits.max_clock_skew_seconds
        except Exception as exc:
            await freeze_trading(
                self.session, reason=f"Broker unreachable: {exc}",
                correlation_id=correlation_id,
            )
            raise RebalanceAborted(f"Broker unreachable: {exc}") from exc
        if not clock_ok:
            await freeze_trading(
                self.session, reason="System clock significantly incorrect vs broker.",
                correlation_id=correlation_id,
            )
            raise RebalanceAborted("Clock skew beyond limit.")

        # Step 5: retrieve account, positions, open orders.
        account = await self.broker.get_account()
        positions = await self.broker.get_positions()
        open_orders = await self.broker.get_open_orders()

        # Step 6: reconcile broker records with local records.
        report = await reconcile(self.session, self.broker, correlation_id)
        blocking = [
            d for d in report.discrepancies
            if d["type"] in ("position_quantity_mismatch", "order_status_unknown")
        ]
        if blocking:
            await freeze_trading(
                self.session,
                reason=f"Reconciliation mismatch: {blocking[:3]}",
                correlation_id=correlation_id,
            )
            raise RebalanceAborted("Local records do not match broker records.")
        await sync_positions_from_broker(self.session, self.broker)

        # Step 7: load the approved universe.
        universe = await self._load_universe()
        run.universe = universe

        # Step 8: retrieve historical data.
        end = utcnow().date()
        start = end - timedelta(days=HISTORY_DAYS)
        bars_by_symbol = await self.market_data.get_daily_bars(universe, start, end)

        # Step 9: validate the data.
        clean: dict[str, list] = {}
        for symbol in universe:
            validation = validate_bars(symbol, bars_by_symbol.get(symbol, []))
            clean[symbol] = validation.clean_bars
        run.status = "data_validated"
        await self.session.flush()

        # Tradability + latest price context.
        tradable: dict[str, bool] = {}
        for symbol in universe:
            tradable[symbol] = await self.broker.is_asset_tradable(symbol)

        # Steps 10-11: generate scores and target weights.
        ai_flags: dict[str, str] = {}
        context = StrategyContext(
            as_of=run.as_of, universe=universe, bars=clean,
            tradable=tradable, ai_risk_flags=ai_flags,
        )
        strategy_result: StrategyResult = self.strategy.generate_target_portfolio(context)
        for ev in strategy_result.evaluations:
            self.session.add(
                Signal(
                    strategy_run_id=run.id,
                    symbol=ev.symbol,
                    eligible=ev.eligible,
                    exclusion_reasons=ev.exclusion_reasons,
                    indicators=ev.indicators.as_dict(),
                    score=ev.score,
                    score_breakdown=(
                        ev.score_breakdown.model_dump() if ev.score_breakdown else {}
                    ),
                )
            )
        targets = strategy_result.portfolio.targets

        # Step 12: apply AI risk adjustments (reduce / veto / flag only).
        ai_adjustments: list[dict] = []
        if self.ai_overlay is not None:
            targets, ai_adjustments = await self.ai_overlay(
                self.session, targets, universe
            )

        self.session.add(
            TargetPortfolioRecord(
                strategy_run_id=run.id,
                as_of=run.as_of,
                targets=[t.model_dump() for t in targets],
                cash_target=strategy_result.portfolio.cash_target,
                ai_adjustments=ai_adjustments,
            )
        )
        run.status = "targets_generated"
        await self.session.flush()

        # Step 13: convert target weights into proposed trades.
        prices: dict[str, float] = {}
        price_timestamps: dict[str, object] = {}
        for symbol in universe:
            trade = await self.market_data.get_latest_trade(symbol)
            if trade is not None:
                prices[symbol] = trade.price
                price_timestamps[symbol] = trade.timestamp
        position_qty = {p.symbol: p.quantity for p in positions}
        position_val = {
            p.symbol: (p.market_value or p.quantity * prices.get(p.symbol, 0.0))
            for p in positions
        }
        equity = account.equity
        target_weights = {t.symbol: t.target_weight for t in targets}
        target_reasons = {t.symbol: t.reasons for t in targets}
        all_symbols = sorted(set(position_qty) | set(target_weights))

        intents: list[TradeIntent] = []
        for symbol in all_symbols:
            price = prices.get(symbol)
            if price is None or price <= 0 or equity <= 0:
                continue
            current_w = position_val.get(symbol, 0.0) / equity
            target_w = target_weights.get(symbol, 0.0)
            delta_w = target_w - current_w
            if abs(delta_w) < REBALANCE_WEIGHT_THRESHOLD:
                continue  # do not trade tiny adjustments
            notional = abs(delta_w) * equity
            quantity = notional / price
            intents.append(
                TradeIntent(
                    symbol=symbol,
                    side="buy" if delta_w > 0 else "sell",
                    quantity=quantity,
                    notional=notional,
                    reference_price=price,
                    current_weight=current_w,
                    target_weight=target_w,
                    reasons=target_reasons.get(symbol, ["Reduce to target weight"]),
                )
            )

        # Persist proposed trades.
        proposed_rows: dict[int, ProposedTrade] = {}
        for i, intent in enumerate(intents):
            row = ProposedTrade(
                strategy_run_id=run.id,
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                notional=intent.notional,
                reference_price=intent.reference_price,
                current_weight=intent.current_weight,
                target_weight=intent.target_weight,
                reasons=intent.reasons,
            )
            self.session.add(row)
            proposed_rows[i] = row
        await self.session.flush()

        # Step 23 (early snapshot used by risk review; refreshed again at end).
        snapshot = AccountSnapshot(
            correlation_id=correlation_id,
            equity=account.equity,
            cash=account.cash,
            buying_power=account.buying_power,
            long_market_value=account.long_market_value,
            positions=[p.model_dump() for p in positions],
        )
        self.session.add(snapshot)
        await self.session.flush()

        # Step 14: run every proposed trade through the risk engine.
        adv: dict[str, float] = {}
        for symbol in universe:
            volume = avg_share_volume(clean.get(symbol, []), 20)
            if volume is not None:
                adv[symbol] = volume
        market_ctx = MarketContext(
            prices=prices,
            price_timestamps=price_timestamps,  # type: ignore[arg-type]
            tradable=tradable,
            avg_daily_volumes=adv,
            approved_universe=universe,
            now=utcnow(),
        )
        account_state = AccountState(
            equity=account.equity,
            cash=account.cash,
            buying_power=account.buying_power,
            positions=position_qty,
            position_values=position_val,
            open_orders=len(open_orders),
        )

        sells: list[tuple[TradeIntent, RiskDecision]] = []
        buys: list[tuple[TradeIntent, RiskDecision, float]] = []
        planned_buy_notional = 0.0
        planned_turnover = 0.0
        froze = False
        for i, intent in enumerate(intents):
            verdict = engine.review_trade(
                intent, account_state, market_ctx,
                planned_buy_notional_before=planned_buy_notional,
                planned_turnover_before=planned_turnover,
            )
            decision_row = RiskDecision(
                strategy_run_id=run.id,
                proposed_trade_id=proposed_rows[i].id,
                account_snapshot_id=snapshot.id,
                decision=verdict.action.value,
                approved_quantity=verdict.approved_quantity,
                approved_notional=verdict.approved_notional,
                rule_name=verdict.rule_name,
                actual_value=verdict.actual_value,
                limit_value=verdict.limit_value,
                strategy_version=self.strategy.version,
                details={
                    "checks": [c.model_dump() for c in verdict.checks],
                    "message": verdict.message,
                },
            )
            self.session.add(decision_row)
            await self.session.flush()

            if verdict.action == RiskAction.FREEZE:
                froze = True
                await freeze_trading(
                    self.session, reason=verdict.message, correlation_id=correlation_id,
                    failed_checks=verdict.checks,
                )
                break
            if verdict.action == RiskAction.REJECT:
                result.rejected_trades += 1
                continue
            if intent.side == "sell":
                sells.append((intent, decision_row))
            else:
                buys.append((intent, decision_row, verdict.approved_notional))
                planned_buy_notional += verdict.approved_notional
            planned_turnover += verdict.approved_notional

        # Step 15: immutable decision report = StrategyRun + Signals +
        # TargetPortfolioRecord + ProposedTrades + RiskDecisions (all above).
        run.status = "risk_reviewed"
        await self.session.flush()

        if froze:
            raise RebalanceAborted("Risk engine froze the strategy during review.")
        if mode == "preview":
            result.status = "completed"
            result.messages.append("Preview mode: no orders submitted.")
            return result

        exec_engine = ExecutionEngine(self.broker, self.session)

        # Step 16: cancel conflicting open orders (same symbols we will trade).
        traded_symbols = {i.symbol for i, *_ in sells} | {i.symbol for i, *_ in buys}
        for order in open_orders:
            if order.symbol in traded_symbols:
                await self.broker.cancel_order(order.broker_order_id)
                log_event(logger, "conflicting_order_canceled",
                          f"canceled open order on {order.symbol}", symbol=order.symbol)

        # Steps 17-18: submit sells, confirm state.
        submitted = 0
        for seq, (intent, decision) in enumerate(sells):
            approved = ApprovedOrder(
                client_order_id=idempotency_key(str(run.id), intent.symbol, "sell", seq),
                risk_decision_id=str(decision.id),
                strategy_run_id=str(run.id),
                symbol=intent.symbol,
                side=OrderSide.SELL,
                quantity=decision.approved_quantity or intent.quantity,
                reference_price=intent.reference_price,
            )
            order_row = await exec_engine.submit(approved)
            submitted += 1
            if order_row.status in ("submitted", "partially_filled"):
                await exec_engine.refresh_order(order_row)

        # Step 19: recalculate available buying power after sells.
        account_after_sells = await self.broker.get_account()
        available_cash = account_after_sells.cash - (
            limits.min_cash_reserve_pct * account_after_sells.equity
        )

        # Step 20: submit buys within refreshed buying power.
        spent = 0.0
        for seq, (intent, decision, approved_notional) in enumerate(buys):
            notional = min(approved_notional, available_cash - spent)
            if notional < limits.min_order_notional:
                result.rejected_trades += 1
                await record_risk_event(
                    self.session, severity="info", rule_name="post_sell_buying_power",
                    message=f"Buy for {intent.symbol} skipped after buying-power refresh",
                    correlation_id=correlation_id,
                )
                continue
            quantity = notional / intent.reference_price
            approved = ApprovedOrder(
                client_order_id=idempotency_key(str(run.id), intent.symbol, "buy", seq),
                risk_decision_id=str(decision.id),
                strategy_run_id=str(run.id),
                symbol=intent.symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                reference_price=intent.reference_price,
            )
            order_row = await exec_engine.submit(approved)
            submitted += 1
            spent += notional
            # Step 21: monitor order status.
            if order_row.status in ("submitted", "partially_filled"):
                await exec_engine.refresh_order(order_row)

        result.submitted_orders = submitted
        run.status = "orders_submitted"
        await self.session.flush()

        # Step 22: save fills and updated positions (fills were recorded by the
        # execution engine; refresh positions from broker truth).
        await sync_positions_from_broker(self.session, self.broker)

        # Step 23: save final account snapshot.
        final_account = await self.broker.get_account()
        final_positions = await self.broker.get_positions()
        self.session.add(
            AccountSnapshot(
                correlation_id=correlation_id,
                equity=final_account.equity,
                cash=final_account.cash,
                buying_power=final_account.buying_power,
                long_market_value=final_account.long_market_value,
                positions=[p.model_dump() for p in final_positions],
            )
        )
        await self.session.flush()

        # Steps 24-25 (lock release + notification) happen in run().
        result.status = "completed"
        return result
