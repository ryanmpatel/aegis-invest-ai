"""Run a backtest end-to-end and persist results."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger, log_event
from app.models.backtesting import (
    BacktestDailyResult,
    BacktestPosition,
    BacktestRun,
    BacktestTrade,
)
from app.services.backtesting.engine import BacktestConfig, BacktestEngine, default_split_labels
from app.services.backtesting.metrics import compute_metrics
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.quality import validate_bars
from app.services.strategies.registry import build_strategy
from app.utils.timeutils import utcnow

logger = get_logger("backtesting.runner")


async def run_backtest(
    session: AsyncSession,
    market_data: MarketDataProvider,
    *,
    strategy_name: str,
    strategy_parameters: dict | None,
    config: BacktestConfig,
) -> BacktestRun:
    strategy = build_strategy(strategy_name, strategy_parameters)
    run = BacktestRun(
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        status="running",
        started_at=utcnow(),
        parameters={
            "start": config.start.isoformat(),
            "end": config.end.isoformat(),
            "starting_capital": config.starting_capital,
            "universe": config.universe,
            "benchmark_symbol": config.benchmark_symbol,
            "rebalance_frequency": config.rebalance_frequency,
            "commission_per_trade": config.commission_per_trade,
            "spread_bps": config.spread_bps,
            "slippage_bps": config.slippage_bps,
            "risk_free_annual": config.risk_free_annual,
            "strategy_parameters": strategy_parameters or {},
            "splits": config.split_labels or default_split_labels(config.start, config.end),
            "dividends": "not modeled by current data provider (disclosed)",
        },
    )
    session.add(run)
    await session.flush()

    try:
        fetch_symbols = list(config.universe)
        if config.benchmark_symbol and config.benchmark_symbol not in fetch_symbols:
            fetch_symbols.append(config.benchmark_symbol)
        data_start = config.start - timedelta(days=int(config.warmup_days * 1.6))
        raw_bars = await market_data.get_daily_bars(fetch_symbols, data_start, config.end)

        bars: dict[str, list] = {}
        for symbol, series in raw_bars.items():
            validation = validate_bars(symbol, series)
            bars[symbol] = validation.clean_bars
            for _, reason in validation.rejected:
                run.warnings = [*run.warnings, f"{symbol}: bar rejected ({reason})"]

        engine = BacktestEngine(strategy, bars, config)
        output = engine.run()

        dates = [row.result_date for row in output.daily]
        equity = [row.equity for row in output.daily]
        benchmark = [row.benchmark_equity for row in output.daily]
        benchmark_clean = (
            [b for b in benchmark if b is not None] if any(benchmark) else None
        )
        invested_fraction = [
            (row.invested_value / row.equity) if row.equity > 0 else 0.0
            for row in output.daily
        ]
        metrics, warnings = compute_metrics(
            dates, equity,
            benchmark_clean if benchmark_clean and len(benchmark_clean) == len(equity) else None,
            [
                {
                    "notional": t.notional,
                    "realized_pl": t.realized_pl,
                    "holding_days": t.holding_days,
                }
                for t in output.trades
            ],
            invested_fraction,
            config.risk_free_annual,
        )
        run.metrics = metrics
        run.warnings = [*run.warnings, *output.warnings, *warnings]
        run.status = "completed"

        session.add_all(
            BacktestDailyResult(
                backtest_run_id=run.id,
                result_date=row.result_date,
                equity=row.equity,
                cash=row.cash,
                invested_value=row.invested_value,
                daily_return=row.daily_return,
                drawdown=row.drawdown,
                benchmark_equity=row.benchmark_equity,
            )
            for row in output.daily
        )
        session.add_all(
            BacktestTrade(
                backtest_run_id=run.id,
                trade_date=t.trade_date,
                symbol=t.symbol,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                commission=t.commission,
                slippage_cost=t.slippage_cost,
                reason=t.reason,
            )
            for t in output.trades
        )
        # Persist weekly position snapshots to bound row counts.
        sampled: list[date] = dates[::5]
        for d in sampled:
            positions = output.positions_by_date.get(d, {})
            day_row = next(r for r in output.daily if r.result_date == d)
            for symbol, qty in positions.items():
                if qty <= 0:
                    continue
                price = engine._last_known_price(symbol, d) or 0.0
                session.add(
                    BacktestPosition(
                        backtest_run_id=run.id,
                        as_of_date=d,
                        symbol=symbol,
                        quantity=qty,
                        price=price,
                        market_value=qty * price,
                        weight=(qty * price / day_row.equity) if day_row.equity > 0 else 0.0,
                    )
                )
    except Exception as exc:
        run.status = "failed"
        run.error = f"{exc.__class__.__name__}: {exc}"
        log_event(logger, "backtest_failed", run.error, backtest_run_id=str(run.id))
        raise
    finally:
        run.finished_at = utcnow()
        await session.flush()

    log_event(
        logger, "backtest_completed",
        f"Backtest {run.id} completed with {len(run.warnings)} warnings",
        backtest_run_id=str(run.id),
    )
    return run


def make_config(payload: dict) -> BacktestConfig:
    """Build a BacktestConfig from API/script input with validation."""
    start = date.fromisoformat(str(payload["start"]))
    end = date.fromisoformat(str(payload["end"]))
    if end <= start:
        raise ValueError("Backtest end date must be after start date.")
    if end > utcnow().date():
        raise ValueError("Backtest end date cannot be in the future.")
    capital = float(payload.get("starting_capital", 100_000.0))
    if capital <= 0:
        raise ValueError("Starting capital must be positive.")
    universe = [str(s).upper() for s in payload.get("universe", [])]
    if not universe:
        raise ValueError("Universe must contain at least one symbol.")
    return BacktestConfig(
        start=start,
        end=end,
        starting_capital=capital,
        universe=universe,
        benchmark_symbol=(payload.get("benchmark_symbol") or "SPY"),
        rebalance_frequency=str(payload.get("rebalance_frequency", "weekly")),
        commission_per_trade=float(payload.get("commission_per_trade", 0.0)),
        spread_bps=float(payload.get("spread_bps", 2.0)),
        slippage_bps=float(payload.get("slippage_bps", 5.0)),
        risk_free_annual=float(payload.get("risk_free_annual", 0.0)),
    )
