# Broker Integration

## Interface

`BrokerClient` (`backend/app/services/broker/base.py`) is the only broker
abstraction. Implementations:

1. **`MockBrokerClient`** — in-memory, deterministic, with injectable failure
   modes (`reject`, `partial`, `timeout`, `unavailable`). Used in development
   and by the entire test suite.
2. **`AlpacaPaperBrokerClient`** — Alpaca **paper** trading via `alpaca-py`.

There is no live adapter, and the factory (`broker/factory.py`) has no branch
that could return one.

## Paper-mode enforcement (Alpaca)

- `TradingClient(..., paper=True)` is hard-coded; no parameter exposes it.
- Construction fails if `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_API_SECRET`
  are missing.
- `get_account()` verifies the account number starts with `PA` (Alpaca paper
  prefix) and refuses to proceed otherwise.
- Secrets live in `SecretStr` settings and are redacted from all logs.

## Order safety

- **Idempotency**: `client_order_id = sha256(run_id:symbol:side:seq)` — the same
  run can never submit the same trade twice, and Alpaca enforces client-id
  uniqueness server-side as a second layer.
- **Duplicate detection**: before submitting, the engine checks its local
  `orders` table and asks the broker for the client id.
- **No blind retries**: reads retry with exponential backoff
  (`app/utils/retry.py`); order submission never does. A timeout after send
  raises `UncertainSubmissionError`, and the engine then *confirms* the order's
  existence by client id before recording the outcome. An unresolved status is
  a reconciliation discrepancy that freezes trading.
- **Tradability check**: `is_asset_tradable` is verified immediately before
  every submission.
- **Lifecycle recording**: every submission attempt, state change, fill,
  cancel, rejection, and expiry is appended to `order_events`.

## Reconciliation

`execution/reconciliation.py` compares local current positions and open orders
against the broker before every rebalance. Quantity mismatches and
unknown-status orders **freeze trading**; missing local state is refreshed from
the broker (broker is the source of truth for positions).

## Getting paper credentials

1. Create an account at <https://alpaca.markets> (no funding required).
2. Open the dashboard, switch to **Paper Trading**, and generate an API key pair.
3. Put them in `.env` as `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_API_SECRET`,
   set `BROKER_PROVIDER=alpaca_paper`, restart, then run
   `make verify-paper-account` (read-only; places no orders).
