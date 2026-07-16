"""Performance statistics.

All functions handle divide-by-zero and insufficient data by returning None
rather than misleading numbers. ``compute_metrics`` adds warnings when the
sample is too short for a statistic to be meaningful.

Alpha/beta methodology: OLS regression of strategy daily returns on benchmark
daily returns; alpha is annualized by multiplying the daily intercept by 252.
The risk-free rate defaults to 0 and is configurable — this is disclosed, not
hidden.
"""

from __future__ import annotations

import math
from typing import Any

TRADING_DAYS = 252
MIN_DAYS_FOR_RATIOS = 60


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _std(xs: list[float], ddof: int = 1) -> float | None:
    if len(xs) <= ddof:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - ddof)
    return math.sqrt(var)


def total_return(equity: list[float]) -> float | None:
    if len(equity) < 2 or equity[0] <= 0:
        return None
    return equity[-1] / equity[0] - 1.0


def annualized_return(equity: list[float]) -> float | None:
    tr = total_return(equity)
    if tr is None:
        return None
    years = (len(equity) - 1) / TRADING_DAYS
    if years <= 0 or (1 + tr) <= 0:
        return None
    return (1 + tr) ** (1 / years) - 1.0


def annualized_volatility(returns: list[float]) -> float | None:
    sd = _std(returns)
    if sd is None:
        return None
    return sd * math.sqrt(TRADING_DAYS)


def sharpe_ratio(returns: list[float], risk_free_annual: float = 0.0) -> float | None:
    if len(returns) < MIN_DAYS_FOR_RATIOS:
        return None
    rf_daily = risk_free_annual / TRADING_DAYS
    excess = [r - rf_daily for r in returns]
    sd = _std(excess)
    m = _mean(excess)
    if sd is None or sd == 0 or m is None:
        return None
    return (m / sd) * math.sqrt(TRADING_DAYS)


def sortino_ratio(returns: list[float], risk_free_annual: float = 0.0) -> float | None:
    if len(returns) < MIN_DAYS_FOR_RATIOS:
        return None
    rf_daily = risk_free_annual / TRADING_DAYS
    excess = [r - rf_daily for r in returns]
    downside = [min(0.0, r) for r in excess]
    downside_dev = math.sqrt(sum(d * d for d in downside) / len(downside)) if downside else 0
    m = _mean(excess)
    if m is None or downside_dev == 0:
        return None
    return (m / downside_dev) * math.sqrt(TRADING_DAYS)


def max_drawdown(equity: list[float]) -> float | None:
    if len(equity) < 2:
        return None
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def drawdown_series(equity: list[float]) -> list[float]:
    out: list[float] = []
    peak = equity[0] if equity else 0.0
    for value in equity:
        peak = max(peak, value)
        out.append(value / peak - 1.0 if peak > 0 else 0.0)
    return out


def calmar_ratio(equity: list[float]) -> float | None:
    ann = annualized_return(equity)
    mdd = max_drawdown(equity)
    if ann is None or mdd is None or mdd == 0:
        return None
    return ann / abs(mdd)


def beta_alpha(
    returns: list[float], benchmark_returns: list[float], risk_free_annual: float = 0.0
) -> tuple[float | None, float | None]:
    """OLS beta and annualized alpha vs the benchmark."""
    n = min(len(returns), len(benchmark_returns))
    if n < MIN_DAYS_FOR_RATIOS:
        return None, None
    rs, bs = returns[-n:], benchmark_returns[-n:]
    mb = sum(bs) / n
    mr = sum(rs) / n
    cov = sum((b - mb) * (r - mr) for b, r in zip(bs, rs, strict=True)) / (n - 1)
    var_b = sum((b - mb) ** 2 for b in bs) / (n - 1)
    if var_b == 0:
        return None, None
    beta = cov / var_b
    rf_daily = risk_free_annual / TRADING_DAYS
    alpha_daily = (mr - rf_daily) - beta * (mb - rf_daily)
    return beta, alpha_daily * TRADING_DAYS


def tracking_error(returns: list[float], benchmark_returns: list[float]) -> float | None:
    n = min(len(returns), len(benchmark_returns))
    if n < MIN_DAYS_FOR_RATIOS:
        return None
    diffs = [r - b for r, b in zip(returns[-n:], benchmark_returns[-n:], strict=True)]
    sd = _std(diffs)
    return sd * math.sqrt(TRADING_DAYS) if sd is not None else None


def monthly_returns(dates: list[Any], equity: list[float]) -> dict[str, float]:
    """Month-key (YYYY-MM) → return within that month."""
    if len(dates) != len(equity) or len(equity) < 2:
        return {}
    out: dict[str, float] = {}
    month_start_value: float | None = None
    current_month = ""
    prev_value = equity[0]
    for d, value in zip(dates, equity, strict=True):
        key = f"{d.year:04d}-{d.month:02d}"
        if key != current_month:
            if current_month and month_start_value and month_start_value > 0:
                out[current_month] = prev_value / month_start_value - 1.0
            current_month = key
            month_start_value = prev_value
        prev_value = value
    if current_month and month_start_value and month_start_value > 0:
        out[current_month] = prev_value / month_start_value - 1.0
    return out


def compute_metrics(
    dates: list[Any],
    equity: list[float],
    benchmark_equity: list[float] | None,
    trades: list[dict[str, Any]],
    invested_fraction: list[float] | None = None,
    risk_free_annual: float = 0.0,
) -> tuple[dict[str, Any], list[str]]:
    """Compute the full statistics block. Returns (metrics, warnings)."""
    warnings: list[str] = []
    if len(equity) < MIN_DAYS_FOR_RATIOS:
        warnings.append(
            f"Backtest span is only {len(equity)} trading days; ratio statistics "
            "(Sharpe, Sortino, alpha/beta) are suppressed as they would be misleading."
        )

    returns = [
        equity[i] / equity[i - 1] - 1.0
        for i in range(1, len(equity))
        if equity[i - 1] > 0
    ]
    bench_returns: list[float] = []
    if benchmark_equity and len(benchmark_equity) == len(equity):
        bench_returns = [
            benchmark_equity[i] / benchmark_equity[i - 1] - 1.0
            for i in range(1, len(benchmark_equity))
            if benchmark_equity[i - 1] > 0
        ]

    # Trade statistics on round-trip realized P&L.
    realized = [t["realized_pl"] for t in trades if t.get("realized_pl") is not None]
    wins = [g for g in realized if g > 0]
    losses = [loss for loss in realized if loss < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    holding_periods = [
        t["holding_days"] for t in trades if t.get("holding_days") is not None
    ]
    monthly = monthly_returns(dates, equity)
    beta, alpha = (
        beta_alpha(returns, bench_returns, risk_free_annual)
        if bench_returns else (None, None)
    )

    turnover_notional = sum(abs(t.get("notional", 0.0)) for t in trades)
    avg_equity = _mean(equity)

    metrics: dict[str, Any] = {
        "total_return": total_return(equity),
        "annualized_return": annualized_return(equity),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns, risk_free_annual),
        "sortino_ratio": sortino_ratio(returns, risk_free_annual),
        "max_drawdown": max_drawdown(equity),
        "calmar_ratio": calmar_ratio(equity),
        "win_rate": (len(wins) / len(realized)) if realized else None,
        "average_gain": _mean(wins),
        "average_loss": _mean(losses),
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "turnover": (turnover_notional / avg_equity) if avg_equity else None,
        "number_of_trades": len(trades),
        "average_holding_period_days": _mean([float(h) for h in holding_periods]),
        "best_month": max(monthly.values()) if monthly else None,
        "worst_month": min(monthly.values()) if monthly else None,
        "pct_time_invested": _mean(invested_fraction) if invested_fraction else None,
        "benchmark_return": total_return(benchmark_equity) if benchmark_equity else None,
        "excess_return": None,
        "tracking_error": tracking_error(returns, bench_returns) if bench_returns else None,
        "beta": beta,
        "alpha_annualized": alpha,
        "risk_free_rate_assumed": risk_free_annual,
        "trading_days": len(equity),
    }
    if metrics["total_return"] is not None and metrics["benchmark_return"] is not None:
        metrics["excess_return"] = metrics["total_return"] - metrics["benchmark_return"]
    return metrics, warnings
