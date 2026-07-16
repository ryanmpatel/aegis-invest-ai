# Weekly Multi-Factor Trend Strategy

**This is an educational starter strategy. It is not a claim of profitability,
and simulated results do not predict real returns.**

## Universe

A configurable list of highly liquid stocks/ETFs (default: SPY, QQQ, IWM, EFA,
AGG, GLD, VNQ, XLE), editable from Settings. Before a symbol is even scored it
must have: tradable status, ≥ 210 daily bars, ≥ $5M average daily dollar
volume (20d), price ≥ $5, and non-stale data (≤ 5 days old).

## Indicators (all computed on adjusted closes)

SMA 20/50/200, 21-day realized volatility (annualized), 63- and 126-day
momentum, 20-day average dollar volume, distance from 52-week high, and
maximum drawdown over 63 days.

## Eligibility

A security is eligible when **all** hold:

1. Latest price > 200-day SMA
2. 50-day SMA > 200-day SMA
3. Liquidity floor met
4. No critical AI risk flag
5. All required indicators computable (no missing data)

Exclusion reasons are stored per symbol per run and shown on the Strategy page.

## Scoring (0..1)

```
raw   = 0.35·squash(momentum_63d) + 0.30·squash(momentum_126d) + 0.35·squash(price/SMA200 − 1)
score = raw · (1 − clamp((vol_penalty + drawdown_penalty)/2))
```

where `squash` is a logistic squashing to (0,1), `vol_penalty` scales with
21-day realized volatility, and `drawdown_penalty` scales with the recent
drawdown. The full component breakdown is persisted in the `signals` table for
every run.

## Portfolio construction

1. Take the top-N eligible symbols by score (default N=6, `min_score` 0.35).
2. Weight by inverse volatility (`1/max(vol, 2%)`), normalized.
3. Cap any single position at `max_position_weight` (default 15%, aligned with
   the risk engine's `max_position_pct` so targets are achievable).
4. Whatever is not allocated stays in cash.
5. Rebalance weekly; weight changes below 1% are not traded.

## Parameters

All parameters live in `DEFAULT_PARAMETERS`
(`backend/app/services/strategies/weekly_multi_factor.py`) and can be
overridden per strategy definition. Defaults are conservative starting points,
not tuned optima. When tuning, use the train/validation/test date splits the
backtester records and report only out-of-sample results.
