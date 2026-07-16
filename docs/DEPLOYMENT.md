# Deployment — putting AegisInvest on the web

The app is two services (FastAPI backend, Next.js frontend) plus Postgres and
Redis. The frontend proxies `/api/*` to the backend server-side (Next
rewrites), so the session cookie stays first-party and no cross-origin cookie
gymnastics are needed — the only URL the browser ever talks to is the frontend.

> Deploying makes your dashboard reachable from the internet. Before doing it:
> set a **strong password**, a **random `APP_SECRET_KEY`**, and
> `SESSION_COOKIE_SECURE=true`. The kill switch and risk engine protect the
> paper account, but the login page is your front door.

## Option A — Render (easiest, ~15 minutes)

1. Push this repo to GitHub (`git init`, commit, push).
2. Create a Render account, then **New → Blueprint** and select the repo — it
   reads [`render.yaml`](../render.yaml) and provisions backend, frontend,
   Postgres, and Redis.
3. When prompted, fill the secret env vars:
   - `AUTH_PASSWORD_HASH` — generate locally:
     `python -c "from app.utils.security import hash_password; print(hash_password('your-password'))"`
   - `CORS_ORIGINS` → `https://<aegis-frontend>.onrender.com`
   - `BACKEND_INTERNAL_URL` (on the frontend) → `https://<aegis-backend>.onrender.com`
   - Alpaca paper keys if you want real market data (optional).
4. Open the frontend URL, sign in, run `make seed` equivalent by hitting
   Settings → universe (or shell into the backend service and run
   `python ../scripts/seed_database.py`).

## Option B — a VPS with Docker Compose (most control)

Any $5–10/month VM (Hetzner, DigitalOcean, Lightsail):

```bash
git clone <your repo> && cd aegis-invest-ai
cp .env.example .env   # set APP_SECRET_KEY, AUTH_PASSWORD_HASH, etc.
docker compose up -d --build
```

Then put a reverse proxy with TLS in front (Caddy is the least effort):

```
# Caddyfile
yourdomain.com {
    reverse_proxy localhost:3000
}
```

Caddy auto-provisions HTTPS. Set `SESSION_COOKIE_SECURE=true` and
`CORS_ORIGINS=https://yourdomain.com` in `.env`.

## Option C — Railway / Fly.io

Both deploy the two Dockerfiles directly (`backend/Dockerfile`,
`frontend/Dockerfile`) with managed Postgres/Redis add-ons. Wire the same env
vars as in Option A.

## Why not Vercel-only?

Vercel is great for the frontend but cannot host the Python backend, the
scheduler (a long-running process), Postgres, or Redis. If you use Vercel for
the frontend, host the backend on Render/Railway/Fly and set
`BACKEND_INTERNAL_URL` to it.

## Production checklist

- [ ] `APP_ENV=production` (disables the dev table-autocreate and `/api/docs`)
- [ ] Long random `APP_SECRET_KEY` (the config refuses the dev default)
- [ ] Strong `AUTH_PASSWORD_HASH`
- [ ] `SESSION_COOKIE_SECURE=true` (HTTPS only)
- [ ] `CORS_ORIGINS` set to the exact frontend origin
- [ ] Run migrations: `alembic upgrade head` (the compose file does this on boot)
- [ ] Secrets entered in the host's secret manager — never committed
- [ ] `LIVE_TRADING_ENABLED` stays `false` (anything else refuses to boot)
