# Risk Model

The risk engine (`backend/app/services/risk/engine.py`) is deterministic: the
same inputs always produce the same verdict, it performs no I/O, and its
decision **overrides** both the strategy and the AI layer. Verdicts are
`approve`, `resize`, `reject`, or `freeze`.

All limits are configurable (Settings → Risk limits) and stored in the active
`RiskProfile`. The defaults below are deliberately conservative starting
values — none are claimed to be optimal.

## Account rules

| Rule | Default | Behavior |
|---|---|---|
| Leverage | never | Buys are capped at available cash; there is no margin path |
| Shorting | never | Sells are capped at held quantity (resize) or rejected |
| Min cash reserve | 5% of equity | Buys resized to preserve the reserve |
| Max total invested | 95% of equity | Buys resized into remaining headroom |
| Max daily turnover | 35% of equity | Cumulative across the rebalance batch |
| Max open positions | 10 | New symbols rejected beyond the cap |
| Max new capital per rebalance | 50% of equity | Cumulative across the batch |

## Position rules

| Rule | Default |
|---|---|
| Max position (fraction of equity) | 15% |
| Max position ($) | $25,000 |
| Min order value | $100 (post-resize dust is rejected) |
| Max order value | $10,000 |
| Max fraction of avg daily volume | 1% |
| Min price | $5 |
| Non-tradable / stale price / outside approved universe | reject |

## Loss & drawdown rules (freeze conditions)

| Rule | Default | On breach |
|---|---|---|
| Daily account loss | 3% | freeze |
| Strategy drawdown | 15% | freeze |
| Portfolio volatility (ann.) | 35% | freeze |
| Consecutive errors | 3 | freeze |
| Consecutive rejected orders | 3 | freeze |
| Per-position stop-loss alert | 15% | risk event (alert, no auto-liquidation) |

When an account-level limit is hit the system: cancels pending buy orders,
blocks new purchases, records a critical `RiskEvent`, disables the scheduler
(`SchedulerConfig.trading_allowed=false`), and requires manual reactivation
(Settings → Risk recovery). Positions are **never** auto-liquidated unless the
user explicitly configures `auto_liquidate_on_limit=true` (default false).

## Operational freeze conditions

Trading freezes when: market data is stale; the broker is unreachable; local
positions do not match broker positions; the same job runs twice (lock
conflict); the database is unavailable; the strategy version is unknown; a
calculation yields NaN/∞; system clock skew exceeds 120s vs the broker clock;
an order has unresolved/unknown status; or the kill switch is active.

## Record keeping

Every rejected or resized trade records: the proposed trade, the rule that
fired, the actual value, the allowed limit, timestamp, strategy version,
account snapshot id, and the full list of rule checks (passed and failed) —
see the `risk_decisions` table and the Activity page.
