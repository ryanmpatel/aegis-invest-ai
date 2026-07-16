# AegisInvest AI

An automated investing **research, backtesting, and paper-trading** platform.
It analyzes daily market data, generates explainable investment signals,
enforces strict deterministic risk rules, and executes simulated trades
through a brokerage **paper-trading** API.

> **Safety first — read this before anything else**
>
> - This is **educational software**. Nothing in it is investment advice.
> - **No strategy here is claimed or guaranteed to be profitable.** Simulated
>   results do not predict real returns.
> - **Live trading is permanently disabled** in this codebase. There is no
>   toggle; the app refuses to start a live broker client. See
>   [docs/LIVE_TRADING_CHECKLIST.md](docs/LIVE_TRADING_CHECKLIST.md).
> - Long-only, no leverage, no shorting, no options, no penny stocks, daily
>   bars, weekly rebalancing at most.

## What it does

1. Connect an Alpaca **paper** account (or use the built-in mock broker).
2. Configure the Weekly Multi-Factor Trend strategy and an approved universe.
3. Backtest against historical data with costs, spread, and slippage modeled.
4. Compare performance against a benchmark with 20+ statistics.
5. Run the strategy automatically in paper mode on a weekly schedule.
6. Inspect every signal, score breakdown, rejected trade, order, fill,
   position, and risk event in an append-only audit trail.
7. Stop everything instantly with a **kill switch** (UI, API, or CLI).
8. Optionally use AI news analysis as a risk overlay — it can only *reduce*
   exposure, veto a buy, or flag a position; it can never initiate a purchase.

## Architecture

```
Data & Research → Strategy Engine → Risk Engine → Execution Engine → Broker (paper)
```

Four isolated layers with one-way flow. Only the execution engine can reach the
broker, and it only accepts orders that carry a risk-engine approval record and
an idempotency key. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Stack**: Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic ·
PostgreSQL · Redis · APScheduler · pytest/hypothesis — Next.js · TypeScript ·
Tailwind · TanStack Query · Recharts — Docker Compose · GitHub Actions.

## Quick start (Docker)

```bash
git clone <this repo> && cd aegis-invest-ai
cp .env.example .env
# Edit .env: set APP_SECRET_KEY and AUTH_PASSWORD_HASH (see below)
docker compose up -d --build
# Frontend: http://localhost:3000   API docs: http://localhost:8000/api/docs
```

Generate a password hash:

```bash
cd backend
python -c "from app.utils.security import hash_password; print(hash_password('your-password'))"
```

Put the output in `.env` as `AUTH_PASSWORD_HASH` (username defaults to `admin`).

## Quick start (local, no Docker)

```bash
make install                  # backend venv + frontend npm install
make seed                     # default universe, risk profile, synthetic data
make backend                  # FastAPI on :8000
make frontend                 # Next.js on :3000 (separate terminal)
```

On Windows without `make`, use `.\scripts\make.ps1 <target>`.

By default everything runs on **mock providers** — a deterministic synthetic
market and an in-memory paper broker — so no external accounts or API keys are
needed to explore the full product.

## Alpaca paper account setup

1. Create a free account at <https://alpaca.markets> (no funding needed).
2. In the dashboard switch to **Paper Trading** and generate API keys.
3. In `.env`:

   ```
   BROKER_PROVIDER=alpaca_paper
   MARKET_DATA_PROVIDER=alpaca
   ALPACA_PAPER_API_KEY=...
   ALPACA_PAPER_API_SECRET=...
   ```

4. Restart, then verify (read-only, places no orders):

   ```bash
   make verify-paper-account
   ```

The adapter hard-codes paper mode, refuses to start without paper credentials,
and verifies the connected account is a paper account. See
[docs/BROKER_INTEGRATION.md](docs/BROKER_INTEGRATION.md).

## Environment variables

See [.env.example](.env.example) for the full annotated list. The important ones:

| Variable | Purpose |
|---|---|
| `APP_SECRET_KEY` | Session/CSRF signing — set to a long random string |
| `AUTH_USERNAME` / `AUTH_PASSWORD_HASH` | Dashboard login |
| `DATABASE_URL` / `REDIS_URL` | Storage & locks |
| `BROKER_PROVIDER` | `mock` (default) or `alpaca_paper` |
| `MARKET_DATA_PROVIDER` | `mock` (default) or `alpaca` |
| `AI_PROVIDER` / `AI_API_KEY` | `mock` (default) or `anthropic` |
| `SCHEDULER_ENABLED` / `REBALANCE_CRON` | Weekly automation |
| `LIVE_TRADING_ENABLED` | Must remain `false`; `true` refuses to boot |

## Development commands

```bash
make test          # 172 tests: unit, integration, property/invariant
make lint          # ruff
make typecheck     # mypy
make migrate       # alembic upgrade head
make seed          # seed demo data
make backtest      # CLI backtest against synthetic data
make kill-switch   # activate the kill switch from the terminal
```

## Backtesting

From the dashboard (**Backtests** page): pick dates, capital, universe, costs,
and run. You get an equity curve vs benchmark, drawdown chart, trade list with
CSV export, and the full statistics block (Sharpe, Sortino, max drawdown,
Calmar, win rate, profit factor, turnover, alpha/beta with documented
methodology, and more). Short backtests suppress ratio statistics rather than
display misleading numbers, and every run records train/validation/test date
splits to discourage overfitting. The engine prevents look-ahead by executing
each decision at the *next* day's open.

## Paper trading

- **Run once**: Overview → "Run rebalance once" (asks for confirmation).
- **Scheduled**: Overview → "Start scheduled trading" (requires
  `SCHEDULER_ENABLED=true`); default cron is Mondays 15:00 UTC.
- Every run walks the 25-step workflow: lock → safety checks → reconciliation →
  data validation → scoring → AI overlay → risk review → sells → buys →
  snapshots → notifications. Any failed safety check freezes trading until you
  manually reactivate it in Settings.

## Kill switch

Big red button in the sidebar; also:

```bash
make kill-switch                      # CLI, works even if the frontend is down
# or: POST /api/kill-switch/activate
```

While active: all order submissions are blocked at the execution engine, the
scheduler is disabled, open buy orders are canceled, positions are left
untouched, and a red banner shows across the app. Deactivation is a deliberate
manual action and both events are recorded with actor and reason.

## Testing

```bash
cd backend && python -m pytest -q
```

The suite (172 tests) covers every indicator and risk rule, order idempotency,
uncertain-submission confirmation, partial fills, reconciliation, the kill
switch, the full rebalance workflow, backtest invariants (cash never negative,
no shorts, no look-ahead), AI output validation and prompt-injection
sanitization, plus hypothesis property tests. It runs entirely on mocks and
SQLite — no network, no external APIs.

## Deploying to the web

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The short version: push to
GitHub and use the included [`render.yaml`](render.yaml) blueprint (backend +
frontend + Postgres + Redis in one click), or run Docker Compose on any VPS
behind Caddy for automatic HTTPS. Set a strong password, a random
`APP_SECRET_KEY`, and `SESSION_COOKIE_SECURE=true` before exposing it.

## Screenshots

*(Run the stack locally and capture: Overview, Backtests with equity curve,
Strategy signals, Activity audit log, and the kill-switch banner.)*

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AUTH_PASSWORD_HASH is not configured` on login | Generate a hash (see Quick start) and set it in `.env` |
| `Refusing to start: Alpaca paper credentials are missing` | Set both paper keys or switch `BROKER_PROVIDER=mock` |
| Rebalance aborts with "Trading is frozen" | Review risk events on the Activity page, then Settings → Risk recovery → Reactivate |
| Rebalance aborts with "already in progress" | A previous run holds the lock; wait for TTL (15 min) or check Redis |
| `LIVE_TRADING_ENABLED=true` fails at boot | Intended. Live trading is permanently disabled |
| Backtest ratios show `—` | The window is too short for meaningful statistics; lengthen it |

## Disclaimers

This project is for research and education. It is not a brokerage, not a
financial advisor, and not a recommendation to buy or sell any security.
Simulated or paper results do not guarantee, and often meaningfully overstate,
real-world performance. Consult qualified professionals before risking money.
