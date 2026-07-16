# Security

## Threat model (MVP)

Single-operator, locally hosted application holding paper-trading API keys.
The assets worth protecting are: broker API credentials, the integrity of the
order pipeline (nothing may place orders except the reviewed path), and the
audit trail.

## Controls implemented

### Secrets
- All credentials come from environment variables; `.env` is gitignored and
  `.env.example` contains placeholders only.
- Secrets are held in Pydantic `SecretStr` (never printed by repr/logs).
- The logging layer (`app/utils/redaction.py`) redacts secret-shaped keys and
  values (Alpaca `PK…` keys, bearer tokens, `sk-…`) from every structured log
  and notification.
- Credentials are never returned by any API endpoint; the Settings page shows
  only presence booleans, and account ids are masked.

### Authentication & session
- Single-user login with PBKDF2-HMAC-SHA256 (600k iterations, per-hash salt).
- HMAC-signed, expiring session token in an `HttpOnly`, `SameSite=Lax` cookie
  (`Secure` flag configurable for HTTPS deployments).
- Constant-time comparisons for username, password, tokens.
- Login endpoint rate-limited separately (10/min default).

### CSRF
- Double-submit pattern: the CSRF token is embedded in the signed session
  payload and must be echoed in `X-CSRF-Token` on every state-changing request.

### HTTP hardening
- CORS restricted to configured origins.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on API responses.
- Global per-IP rate limiting (in-process sliding window; swap for Redis when
  multi-node).
- Safe error handler: unhandled exceptions return a generic 500 with no
  internals; details go to structured logs only.
- OpenAPI docs disabled in production.

### Injection
- All database access goes through the SQLAlchemy ORM with bound parameters.
- Universe symbols validated (`isalnum`, length-capped); every request body is
  Pydantic-validated.
- AI prompt injection: article text is length-limited, control characters and
  boundary-breaking tags stripped, wrapped in `<untrusted_article>` with an
  explicit "data, not instructions" system prompt; output is schema-validated
  with `extra="forbid"`; the AI layer can only reduce exposure and has no
  access to broker clients, credentials, balances, or order data.

### Auditability
- Append-only records for orders, order events, fills, risk decisions, risk
  events, kill-switch events, and account snapshots, all correlated by
  `correlation_id` / `strategy_run_id`.

### Dependencies & CI
- CI runs ruff, mypy, and the full test suite on every push.
- `pip-audit` / `npm audit` steps are included in CI for dependency
  vulnerability scanning.

## Deliberate non-goals (MVP)

- Multi-user auth/authorization (single operator).
- At-rest encryption of the database (host-level disk encryption recommended).
- Secrets manager integration — recommended before any cloud deployment
  (use platform secret stores rather than `.env` files).

## Never commit

API keys, database passwords, auth secrets, `.env` files, broker account
information. The `.gitignore` enforces the file patterns; review diffs before
pushing regardless.
