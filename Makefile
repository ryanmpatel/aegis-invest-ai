# AegisInvest AI — developer commands
# On Windows without make, use the equivalent commands in the comments,
# or run scripts/make.ps1 <target>.

PY ?= backend/.venv/bin/python
PIP ?= backend/.venv/bin/pip

.PHONY: install dev backend frontend test lint typecheck migrate seed backtest \
        verify-paper-account kill-switch docker-up docker-down

install:            ## Install backend + frontend dependencies
	cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

dev:                ## Run backend and frontend dev servers together
	$(MAKE) -j2 backend frontend

backend:            ## Run FastAPI dev server
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:           ## Run Next.js dev server
	cd frontend && npm run dev

test:               ## Run backend test suite
	cd backend && .venv/bin/python -m pytest -q

lint:               ## Ruff lint
	cd backend && .venv/bin/python -m ruff check app tests

typecheck:          ## MyPy type check
	cd backend && .venv/bin/python -m mypy app

migrate:            ## Apply database migrations
	cd backend && .venv/bin/alembic upgrade head

seed:               ## Seed the database with demo data
	cd backend && .venv/bin/python ../scripts/seed_database.py

backtest:           ## Run a sample backtest from the CLI
	cd backend && .venv/bin/python ../scripts/run_backtest.py

verify-paper-account: ## Verify Alpaca paper credentials (read-only)
	cd backend && .venv/bin/python ../scripts/verify_broker_connection.py

kill-switch:        ## Activate the kill switch from the CLI
	cd backend && .venv/bin/python -m app.cli kill-switch --activate --reason "CLI activation"

docker-up:          ## Start the full stack
	docker compose up -d --build

docker-down:        ## Stop the full stack
	docker compose down
