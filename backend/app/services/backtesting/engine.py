"""Event-driven backtesting engine.

Shares the Strategy and RiskEngine interfaces with paper trading. Walks
forward day by day; on rebalance days the strategy sees ONLY bars up to and
including that day (no look-ahead), decisions execute at the NEXT day's open
plus costs (no trading on information not yet available at execution time).

Costs modeled: per-trade commission, half-spread, slippage (bps of notional).
Fractional shares are simulated. Cash can never go negative (long-only,
no leverage). Missing symbols simply have no bars — positions in a symbol
whose data ends (delisting proxy) are liquidated at the last known price and
a warning is recorded.

Bias controls: parameters may declare train/validation/test split dates which
are stored with the run for disclosure; the engine itself never reads bars
beyond the current simulation date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from app.schemas.market_data import BarData
from app.schemas.risk import AccountState, MarketContext, RiskAction, RiskLimits, TradeIntent
from app.schemas.strategy import StrategyContext
from app.services.risk.engine import RiskEngine
from app.services.strategies.base import Strategy
from app.utils.timeutils import utcnow


@dataclass
class BacktestConfig:
    start: date
    end: date
    starting_capital: float = 100_000.0
    universe: list[str] = field(default_factory=list)
    benchmark_symbol: str | None = "SPY"
    rebalance_frequency: str = "weekly"  # weekly | monthly
    commission_per_trade: float = 0.0
    spread_bps: float = 2.0        # half-spread applied per side
    slippage_bps: float = 5.0
    risk_free_annual: float = 0.0
    rebalance_weight_threshold: float = 0.01
    warmup_days: int = 300         # history before `start` shown to the strategy
    split_labels: dict[str, str] = field(default_factory=dict)  # disclosure only


@dataclass
class SimTrade:
    trade_date: date
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float
    slippage_cost: float
    notional: float
    reason: str = ""
    realized_pl: float | None = None
    holding_days: int | None = None


@dataclass
class DailyRow:
    result_date: date
    equity: float
    cash: float
    invested_value: float
    daily_return: float | None
    drawdown: float
    benchmark_equity: float | None


@dataclass
class BacktestOutput:
    config: BacktestConfig
    daily: list[DailyRow] = field(default_factory=list)
    trades: list[SimTrade] = field(default_factory=list)
    positions_by_date: dict[date, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    rejected_trades: int = 0


class _Lot:
    __slots__ = ("cost_basis", "opened", "quantity")

    def __init__(self, quantity: float, cost_basis: float, opened: date) -> None:
        self.quantity = quantity
        self.cost_basis = cost_basis
        self.opened = opened


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        bars: dict[str, list[BarData]],
        config: BacktestConfig,
        risk_limits: RiskLimits | None = None,
    ) -> None:
        """``bars`` must include warmup history before config.start and, when
        benchmarking, the benchmark symbol's bars."""
        self.strategy = strategy
        self.config = config
        self.risk_engine = RiskEngine(risk_limits or RiskLimits())
        # Index bars by symbol and date for O(1) lookup; keep ascending lists.
        self.bars = {s: sorted(bs, key=lambda b: b.bar_date) for s, bs in bars.items()}
        self.bar_index: dict[str, dict[date, BarData]] = {
            s: {b.bar_date: b for b in bs} for s, bs in self.bars.items()
        }

    # ------------------------------------------------------------------

    def _trading_days(self) -> list[date]:
        days: set[date] = set()
        for symbol in self.config.universe:
            for b in self.bars.get(symbol, []):
                if self.config.start <= b.bar_date <= self.config.end:
                    days.add(b.bar_date)
        return sorted(days)

    def _is_rebalance_day(self, d: date, prev: date | None) -> bool:
        if prev is None:
            return True
        if self.config.rebalance_frequency == "monthly":
            return d.month != prev.month or d.year != prev.year
        return d.isocalendar()[1] != prev.isocalendar()[1] or d.year != prev.year

    def _history_until(self, symbol: str, until: date) -> list[BarData]:
        """Bars up to and including ``until`` — the no-look-ahead boundary."""
        return [b for b in self.bars.get(symbol, []) if b.bar_date <= until]

    def _price_on(self, symbol: str, d: date, field_name: str = "close") -> float | None:
        bar = self.bar_index.get(symbol, {}).get(d)
        if bar is None:
            return None
        value = getattr(bar, field_name)
        if field_name == "close" and bar.adjusted_close is not None:
            value = bar.adjusted_close
        return float(value)

    def _last_known_price(self, symbol: str, until: date) -> float | None:
        history = self._history_until(symbol, until)
        if not history:
            return None
        last = history[-1]
        return last.adjusted_close if last.adjusted_close is not None else last.close

    # ------------------------------------------------------------------

    def run(self) -> BacktestOutput:
        cfg = self.config
        out = BacktestOutput(config=cfg)
        cash = cfg.starting_capital
        lots: dict[str, _Lot] = {}
        pending_targets: dict[str, float] | None = None
        days = self._trading_days()
        if not days:
            out.warnings.append("No trading days with data in the selected range.")
            return out

        benchmark_start_price: float | None = None
        if cfg.benchmark_symbol:
            benchmark_start_price = self._last_known_price(cfg.benchmark_symbol, days[0])
            if benchmark_start_price is None:
                out.warnings.append(
                    f"Benchmark {cfg.benchmark_symbol} has no data; comparison disabled."
                )

        prev_equity: float | None = None
        prev_day: date | None = None
        last_rebalance_week: date | None = None
        peak_equity = cfg.starting_capital

        for day in days:
            # 1) Execute targets decided on the PREVIOUS rebalance day at
            #    today's open (information barrier).
            if pending_targets is not None:
                cash = self._execute_targets(
                    pending_targets, lots, cash, day, out, peak_equity
                )
                pending_targets = None

            # 2) Mark to market at today's close.
            invested = 0.0
            for symbol, lot in list(lots.items()):
                price = self._price_on(symbol, day) or self._last_known_price(symbol, day)
                if price is None:
                    continue
                invested += lot.quantity * price
            equity = cash + invested
            peak_equity = max(peak_equity, equity)
            daily_return = (
                equity / prev_equity - 1.0 if prev_equity and prev_equity > 0 else None
            )
            drawdown = equity / peak_equity - 1.0 if peak_equity > 0 else 0.0

            benchmark_equity = None
            if benchmark_start_price:
                bench_price = self._last_known_price(cfg.benchmark_symbol or "", day)
                if bench_price:
                    benchmark_equity = cfg.starting_capital * (
                        bench_price / benchmark_start_price
                    )

            out.daily.append(
                DailyRow(
                    result_date=day, equity=round(equity, 2), cash=round(cash, 2),
                    invested_value=round(invested, 2), daily_return=daily_return,
                    drawdown=round(drawdown, 6), benchmark_equity=benchmark_equity,
                )
            )
            out.positions_by_date[day] = {s: lot.quantity for s, lot in lots.items()}

            # 3) Detect delisted/missing symbols: liquidate if data has ended.
            for symbol in list(lots):
                future_bars = [
                    b for b in self.bars.get(symbol, [])
                    if day < b.bar_date <= cfg.end
                ]
                has_today = self.bar_index.get(symbol, {}).get(day) is not None
                if not future_bars and not has_today:
                    price = self._last_known_price(symbol, day)
                    if price:
                        lot = lots.pop(symbol)
                        proceeds = lot.quantity * price
                        cash += proceeds
                        out.trades.append(
                            SimTrade(
                                trade_date=day, symbol=symbol, side="sell",
                                quantity=lot.quantity, price=price, commission=0.0,
                                slippage_cost=0.0, notional=proceeds,
                                reason="data_ended_forced_liquidation",
                                realized_pl=proceeds - lot.cost_basis * lot.quantity,
                                holding_days=(day - lot.opened).days,
                            )
                        )
                        out.warnings.append(
                            f"{symbol}: data ended on {day}; position force-liquidated."
                        )

            # 4) On rebalance days, ask the strategy for NEW targets using data
            #    up to today only; execution happens tomorrow.
            if self._is_rebalance_day(day, last_rebalance_week):
                last_rebalance_week = day
                context = StrategyContext(
                    as_of=datetime.combine(day, time(16, 0), tzinfo=UTC),
                    universe=cfg.universe,
                    bars={s: self._history_until(s, day) for s in cfg.universe},
                    tradable={s: bool(self.bars.get(s)) for s in cfg.universe},
                )
                result = self.strategy.generate_target_portfolio(context)
                pending_targets = {
                    t.symbol: t.target_weight for t in result.portfolio.targets
                }

            prev_equity = equity
            prev_day = day

        _ = prev_day
        return out

    # ------------------------------------------------------------------

    def _execute_targets(
        self,
        targets: dict[str, float],
        lots: dict[str, _Lot],
        cash: float,
        day: date,
        out: BacktestOutput,
        peak_equity: float,
    ) -> float:
        cfg = self.config
        # Value portfolio at today's open (execution prices).
        prices: dict[str, float] = {}
        for symbol in set(list(targets) + list(lots)):
            price = self._price_on(symbol, day, "open") or self._last_known_price(symbol, day)
            if price:
                prices[symbol] = price
        invested = sum(
            lot.quantity * prices.get(s, lot.cost_basis) for s, lot in lots.items()
        )
        equity = cash + invested
        if equity <= 0:
            return cash

        cost_multiplier = (cfg.spread_bps + cfg.slippage_bps) / 10_000.0
        drawdown_pct = equity / peak_equity - 1.0 if peak_equity > 0 else 0.0

        account_state = AccountState(
            equity=equity, cash=cash, buying_power=cash,
            positions={s: lot.quantity for s, lot in lots.items()},
            position_values={
                s: lot.quantity * prices.get(s, lot.cost_basis) for s, lot in lots.items()
            },
            drawdown_pct=drawdown_pct,
        )
        now = datetime.combine(day, time(14, 30), tzinfo=UTC)
        market_ctx = MarketContext(
            prices=prices,
            price_timestamps=dict.fromkeys(prices, now),
            tradable=dict.fromkeys(prices, True),
            avg_daily_volumes={},
            approved_universe=list(set(cfg.universe) | set(lots)),
            now=now,
        )

        # Sells first.
        planned_turnover = 0.0
        for symbol, lot in list(lots.items()):
            price = prices.get(symbol)
            if price is None or price <= 0:
                continue
            current_w = lot.quantity * price / equity
            target_w = targets.get(symbol, 0.0)
            delta = target_w - current_w
            if delta >= -cfg.rebalance_weight_threshold:
                continue
            sell_qty = min(lot.quantity, abs(delta) * equity / price)
            intent = TradeIntent(
                symbol=symbol, side="sell", quantity=sell_qty,
                notional=sell_qty * price, reference_price=price,
                current_weight=current_w, target_weight=target_w,
            )
            verdict = self.risk_engine.review_trade(
                intent, account_state, market_ctx,
                planned_turnover_before=planned_turnover,
            )
            if verdict.action == RiskAction.FREEZE:
                out.warnings.append(f"Risk freeze during backtest sell review: {verdict.message}")
                return cash
            if verdict.action == RiskAction.REJECT:
                out.rejected_trades += 1
                continue
            qty = verdict.approved_quantity or sell_qty
            exec_price = price * (1 - cost_multiplier)
            proceeds = qty * exec_price - cfg.commission_per_trade
            if proceeds <= 0:
                out.rejected_trades += 1
                continue
            cash += proceeds
            planned_turnover += qty * exec_price
            realized = (exec_price - lot.cost_basis) * qty - cfg.commission_per_trade
            out.trades.append(
                SimTrade(
                    trade_date=day, symbol=symbol, side="sell", quantity=qty,
                    price=exec_price, commission=cfg.commission_per_trade,
                    slippage_cost=qty * price * cost_multiplier,
                    notional=qty * exec_price, reason="rebalance",
                    realized_pl=realized, holding_days=(day - lot.opened).days,
                )
            )
            lot.quantity -= qty
            if lot.quantity <= 1e-9:
                del lots[symbol]
            account_state.positions[symbol] = lots[symbol].quantity if symbol in lots else 0.0
            account_state.position_values[symbol] = (
                account_state.positions[symbol] * price
            )
            account_state.cash = cash

        # Buys.
        planned_buys = 0.0
        for symbol, target_w in sorted(targets.items(), key=lambda kv: -kv[1]):
            price = prices.get(symbol)
            if price is None or price <= 0:
                continue
            held = lots.get(symbol)
            current_value = held.quantity * price if held else 0.0
            current_w = current_value / equity
            delta = target_w - current_w
            if delta <= cfg.rebalance_weight_threshold:
                continue
            buy_notional = delta * equity
            quantity = buy_notional / price
            intent = TradeIntent(
                symbol=symbol, side="buy", quantity=quantity, notional=buy_notional,
                reference_price=price, current_weight=current_w, target_weight=target_w,
            )
            verdict = self.risk_engine.review_trade(
                intent, account_state, market_ctx,
                planned_buy_notional_before=planned_buys,
                planned_turnover_before=planned_turnover,
            )
            if verdict.action == RiskAction.FREEZE:
                out.warnings.append(f"Risk freeze during backtest buy review: {verdict.message}")
                return cash
            if verdict.action == RiskAction.REJECT:
                out.rejected_trades += 1
                continue
            notional = verdict.approved_notional or buy_notional
            exec_price = price * (1 + cost_multiplier)
            total_cost = notional + cfg.commission_per_trade
            if total_cost > cash:
                notional = cash - cfg.commission_per_trade
                if notional <= 0:
                    out.rejected_trades += 1
                    continue
            qty = notional / exec_price
            cash -= qty * exec_price + cfg.commission_per_trade
            assert cash >= -1e-6, "cash went negative in backtest — invariant violated"
            cash = max(cash, 0.0)
            planned_buys += notional
            planned_turnover += notional
            if held is None:
                lots[symbol] = _Lot(qty, exec_price, day)
            else:
                total_qty = held.quantity + qty
                held.cost_basis = (
                    held.cost_basis * held.quantity + exec_price * qty
                ) / total_qty
                held.quantity = total_qty
            out.trades.append(
                SimTrade(
                    trade_date=day, symbol=symbol, side="buy", quantity=qty,
                    price=exec_price, commission=cfg.commission_per_trade,
                    slippage_cost=qty * price * cost_multiplier,
                    notional=qty * exec_price, reason="rebalance",
                )
            )
            account_state.positions[symbol] = lots[symbol].quantity
            account_state.position_values[symbol] = lots[symbol].quantity * price
            account_state.cash = cash

        return cash


def default_split_labels(start: date, end: date) -> dict[str, str]:
    """Suggest a 60/20/20 train/validation/test date split for disclosure."""
    span = (end - start).days
    train_end = start + timedelta(days=int(span * 0.6))
    val_end = start + timedelta(days=int(span * 0.8))
    return {
        "train": f"{start.isoformat()}..{train_end.isoformat()}",
        "validation": f"{train_end.isoformat()}..{val_end.isoformat()}",
        "test": f"{val_end.isoformat()}..{end.isoformat()}",
        "generated_at": utcnow().isoformat(),
        "note": (
            "Choose strategy parameters on train/validation only; report "
            "out-of-sample results from the test window."
        ),
    }
