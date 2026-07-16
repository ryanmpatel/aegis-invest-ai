# Live Trading Checklist

**Live trading is permanently disabled in this codebase.** `LIVE_TRADING_ENABLED`
is pinned to `false`, the settings validator rejects any attempt to set it to
`true`, and no live broker adapter exists. There is deliberately no "switch to
live" toggle anywhere in the product.

This document exists so that *if* live trading were ever considered in a future,
separate effort, the bar it would have to clear is written down in advance.
Nothing below grants permission; every item requires human judgment and sign-off.

## Prerequisites that must ALL be satisfied first

- [ ] **Extended paper-trading period**: ≥ 6 months of uninterrupted scheduled
      paper trading with zero reconciliation freezes and zero unexplained orders.
- [ ] **Out-of-sample backtest**: strategy parameters chosen on train/validation
      windows only; test-window results documented, including costs.
- [ ] **Walk-forward testing**: rolling re-fit/evaluate cycles documented, with
      stable behavior across regimes.
- [ ] **Slippage stress test**: results remain acceptable at 3–5× assumed
      spread/slippage.
- [ ] **Market-data outage test**: pipeline outage mid-rebalance freezes safely
      and recovers cleanly.
- [ ] **Broker-outage test**: broker unreachable before/during/after submission
      freezes safely; uncertain submissions are confirmed, never re-sent blind.
- [ ] **Duplicate-order test**: forced duplicate scheduler runs and forced
      idempotency-key collisions produce zero duplicate broker orders.
- [ ] **Partial-fill test**: partial fills reconcile correctly and next-run
      targets account for them.
- [ ] **Reconciliation test**: injected position/order mismatches always freeze
      trading before any new order.
- [ ] **Drawdown test**: breaching the drawdown limit halts buying, notifies,
      and requires manual reactivation.
- [ ] **Manual code review**: an independent, qualified reviewer signs off on
      the execution and risk paths.
- [ ] **Small-capital rollout plan**: a written plan starting with an amount the
      owner can afford to lose entirely, with explicit escalation gates.
- [ ] **Brokerage eligibility confirmed**: account type, PDT rules, and
      jurisdiction constraints reviewed.
- [ ] **Tax and regulatory review**: applicable tax treatment and any licensing/
      advice-regulation issues reviewed with qualified professionals.
- [ ] **Manual approval by the account owner**: written, dated, revocable.

## Engineering requirements for any future implementation

Live trading, if ever built, must be a **separate adapter** in a separate
module, using **separate credentials** (never the paper keys), gated by an
**environment-level approval** distinct from application config, and requiring
**interactive manual confirmation** at startup. It must never be reachable by
flipping a value in `.env` on the current codebase.

## A note on expectations

Passing every item above still does not make a strategy profitable. Markets
change; backtests overfit; execution costs compound. Do not risk money you
cannot afford to lose.
