# AegisInvest AI — Implementation Plan

This plan tracks the staged build of the platform. Each stage ends with passing
tests, lint, and type checks. Live trading is out of scope permanently for this
codebase (see `LIVE_TRADING_CHECKLIST.md`).

## Guiding decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend | Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 async | Spec requirement; async fits broker/data IO |
| DB | PostgreSQL (prod), SQLite for tests/dev fallback | Tests must run without Docker |
| Locks | Redis `SET NX PX` lock with process-local fallback in dev | Rebalance must be single-flight |
| Auth | Single-user session cookie (PBKDF2 hash from env) + CSRF token | Local MVP, still authenticated |
| Broker | `BrokerClient` protocol → `MockBrokerClient`, `AlpacaPaperBrokerClient` | Paper only; live client refuses to construct |
| AI | `AIAnalysisProvider` protocol → mock default, Anthropic optional | App fully functional with no AI key |
| Scheduler | APScheduler in-process, guarded by distributed lock + kill switch | MVP scale |
| Backtester | Event-driven daily loop sharing Strategy + RiskEngine interfaces | No look-ahead; same code paths as paper trading |

## Stage checklist

### Stage 1 — Foundation
- [x] Monorepo structure, `.gitignore`, `.env.example`, `DEVELOPMENT.md`, `Makefile`
- [x] Docker Compose (postgres, redis, backend, frontend)
- [x] FastAPI app factory, config system (pydantic-settings), structured JSON logging
- [x] Async SQLAlchemy setup + Alembic migrations
- [x] All database models (config, market data, trading, backtesting)
- [x] Authentication (login/logout, session cookie, CSRF, rate limiting)
- [x] Health + system status endpoints
- [x] Next.js app shell with auth flow and dashboard layout

### Stage 2 — Data & Backtesting
- [x] `MarketDataProvider` protocol; mock provider with deterministic synthetic data
- [x] Alpaca historical data provider (guarded optional import)
- [x] Daily-bar storage + data-quality validation (dupes, gaps, negative prices, future dates, staleness)
- [x] Indicator library (SMA 20/50/200, realized vol, momentum 63/126, dollar volume, 52w-high distance, drawdown)
- [x] `Strategy` protocol + `StrategyContext` + `TargetPortfolio`
- [x] Weekly Multi-Factor Trend strategy with score breakdown persistence
- [x] Event-driven backtesting engine (costs, spread, slippage, fractional shares, benchmark)
- [x] Performance metrics module (Sharpe, Sortino, max DD, Calmar, alpha/beta, etc.)
- [x] Backtest API endpoints + dashboard page (run, equity curve, drawdown, trades, CSV export)

### Stage 3 — Paper Trading
- [x] `BrokerClient` protocol, `MockBrokerClient`, `AlpacaPaperBrokerClient` (paper-mode enforced)
- [x] Order lifecycle records (submit → events → fills), idempotency keys, duplicate detection
- [x] Reconciliation service (local vs broker orders/positions)
- [x] 25-step rebalance workflow with crash recovery
- [x] APScheduler worker with distributed lock
- [x] Portfolio + activity dashboard pages

### Stage 4 — Risk & Safety
- [x] Deterministic risk engine: account, position, loss/drawdown, operational rules
- [x] Freeze semantics + manual reactivation
- [x] Kill switch (API + CLI + UI banner)
- [x] Distributed lock provider (Redis + local fallback)
- [x] Notifications (console, email, webhook) with secret redaction
- [x] Immutable audit trail (risk decisions, risk events, kill-switch events)

### Stage 5 — AI Analysis
- [x] `AIAnalysisProvider` protocol + mock provider
- [x] Anthropic provider with strict JSON schema validation (Pydantic)
- [x] Prompt-injection defenses (untrusted-data framing, length limits, sanitization)
- [x] Risk-overlay integration (reduce/veto/flag only; confidence threshold; neutral on absence)
- [x] AI analysis dashboard surface

### Stage 6 — Hardening
- [x] Full test suite (unit, integration, property/invariant)
- [x] GitHub Actions CI (lint, typecheck, tests)
- [x] Security pass (headers, CORS, cookies, rate limits, redaction)
- [x] Documentation set under `docs/`
- [ ] Screenshots in README (requires a human running the stack)

## Assumptions documented during build

1. Single-user MVP: one operator account configured via env vars; multi-user auth is
   a later concern. All records still carry user-agnostic audit fields.
2. Tests and local dev may use SQLite (aiosqlite); production uses Postgres. JSON
   columns are used (portable) instead of Postgres-only JSONB features.
3. The Alpaca adapters import `alpaca-py` lazily so the mock-only configuration works
   with no Alpaca dependency installed at runtime.
4. Dividends are applied in backtests only when the data provider supplies them;
   the mock provider does not, and this is disclosed in backtest results.
5. Rate limiting is in-process (per-IP sliding window) — adequate for a single-node MVP.
6. "Benchmark" defaults to SPY total-price return (not total-return index) and the
   docs disclose this limitation.
