# AegisInvest AI — Development Guide

Contributor rules and conventions for this repository.

Automated investing research, backtesting, and **paper-trading** platform.
Stocks/ETFs only, daily bars, weekly rebalance, long-only, no leverage, no options.

## Non-negotiable safety rules

1. **Live trading is disabled.** `LIVE_TRADING_ENABLED=false` always. The code refuses
   to construct a live broker client. Never add a live adapter, a "switch to live"
   toggle, or live credentials. See `docs/LIVE_TRADING_CHECKLIST.md`.
2. **Only the execution engine talks to the broker.** Strategies, AI providers, and
   API handlers must never import or call a `BrokerClient` directly.
3. **Every trade passes the deterministic risk engine.** The risk engine's decision
   overrides strategy and AI output. No code path may submit an order without an
   approval record and idempotency key.
4. **AI can only reduce risk.** AI news analysis may reduce exposure, veto a buy, or
   flag a position — never initiate a purchase. Missing AI analysis is neutral.
5. **Kill switch always wins.** When active, no order submission of any kind.
6. **No secrets in code, logs, or notifications.** Credentials come from env vars and
   are redacted by the logging layer. `.env` is gitignored.
7. **Never claim a strategy guarantees profit.** All copy must be educational.

## Architecture (4 layers, one-way flow)

```
Data/Research → Strategy Engine → Risk Engine → Execution Engine → Broker (paper)
```

- `backend/app/services/market_data/` — providers + data-quality validation
- `backend/app/services/strategies/`  — target weights only, no broker access
- `backend/app/services/risk/`        — deterministic rule engine, approve/resize/reject/freeze
- `backend/app/services/execution/`   — sole broker gateway, idempotent orders
- `backend/app/services/backtesting/` — event-driven, same Strategy + Risk interfaces
- `backend/app/services/ai_analysis/` — optional risk overlay, mock by default

## Commands

```bash
make install        # backend deps (uv/pip) + frontend deps (npm)
make dev            # backend + frontend dev servers
make test           # pytest (backend) — must pass before advancing a stage
make lint           # ruff check
make typecheck      # mypy
make migrate        # alembic upgrade head
make seed           # seed database with fake data
make backtest       # run a sample backtest from CLI
make kill-switch    # activate the kill switch from CLI
make docker-up      # full stack via docker compose
```

## Development rules

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic, Postgres, Redis.
- Frontend: Next.js (App Router), TypeScript, Tailwind, TanStack Query, Recharts.
- UUID primary keys, UTC timestamps everywhere (`datetime.now(UTC)`).
- Financial records (orders, fills, risk decisions, snapshots) are append-only.
- Tests use SQLite + mock providers; the suite must not hit external APIs.
- Run `make test && make lint && make typecheck` after every stage; fix before continuing.
- Do not place any order (even paper) during development unless a human runs the command.
