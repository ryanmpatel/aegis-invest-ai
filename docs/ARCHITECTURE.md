# Architecture

AegisInvest AI is built around four isolated layers with strictly one-way flow:

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ 1. Data &       │ → │ 2. Strategy     │ → │ 3. Risk         │ → │ 4. Execution    │ → Broker
│    Research     │   │    Engine       │   │    Engine       │   │    Engine       │   (paper)
└─────────────────┘   └─────────────────┘   └─────────────────┘   └─────────────────┘
```

## Layer boundaries and how they are enforced

| Layer | Package | May talk to broker? | Enforced by |
|---|---|---|---|
| Data & Research | `app/services/market_data`, `ai_analysis` | No | No broker imports; providers expose read-only protocols |
| Strategy | `app/services/strategies` | No | `StrategyContext` contains only bars/flags — no clients, no credentials |
| Risk | `app/services/risk` | No | Pure functions over `AccountState`/`MarketContext` snapshots |
| Execution | `app/services/execution` | **Yes — only here** | `ExecutionEngine.submit` requires an `ApprovedOrder`, which cannot be constructed without a `risk_decision_id` |

Additional hard guards:

- `ApprovedOrder` (Pydantic) requires `risk_decision_id` + `strategy_run_id` + a
  deterministic `client_order_id` — the type system encodes "no unreviewed order".
- `ExecutionEngine.__init__` rejects any broker client with `is_paper=False`.
- `Settings` rejects `LIVE_TRADING_ENABLED=true` at startup (validation error).
- The kill switch is checked inside `ExecutionEngine.submit` — even a code path
  that bypassed the workflow could not submit while it is active.

## Backend components

- **FastAPI** app (`app/main.py`): CORS, security headers, in-process rate limiting,
  safe error handler, session-cookie auth with CSRF double-submit.
- **SQLAlchemy 2 async** + **Alembic**: PostgreSQL in production, SQLite in tests.
  UUID PKs, UTC timestamps, append-only financial records.
- **Rebalance workflow** (`execution/rebalance.py`): the 25-step process from the
  spec — lock → safety checks → reconcile → data → strategy → AI overlay →
  risk review → sells → buys → snapshots → notify. Any failed safety check
  freezes trading and requires manual reactivation.
- **Backtester** (`backtesting/engine.py`): event-driven daily loop that reuses the
  same `Strategy` and `RiskEngine` interfaces. Decisions on day *t* execute at
  day *t+1*'s open with spread/slippage/commission costs.
- **Scheduler** (`workers/scheduler.py`): APScheduler cron job, single-instance,
  guarded by kill switch, freeze state, and the distributed lock.
- **Locks** (`execution/locks.py`): Redis `SET NX PX` with compare-and-delete
  release; process-local fallback for development.

## Frontend

Next.js App Router + TypeScript + Tailwind + TanStack Query + Recharts.
All API calls go through `lib/api.ts`, which attaches the CSRF header. The API
is proxied through Next rewrites so the session cookie stays same-origin.

## Decision trail

Every trade is explainable end to end:

```
DailyBar → Signal (indicators + score breakdown)
        → TargetPortfolioRecord (weights + AI adjustments)
        → ProposedTrade (weight delta → qty)
        → RiskDecision (rule, actual, limit, checks)
        → Order (idempotency key) → OrderEvent* → Fill
        → PositionRecord + AccountSnapshot
```

All rows carry `strategy_run_id` / `correlation_id` and are never mutated after
their lifecycle completes.
