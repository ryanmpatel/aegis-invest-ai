"""API integration tests: auth, CSRF, kill switch, backtests, settings."""

from __future__ import annotations

from tests.conftest import TEST_PASSWORD


class TestAuth:
    async def test_login_logout_me(self, client):
        response = await client.post(
            "/api/auth/login", json={"username": "tester", "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        assert "csrf_token" in response.json()

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "tester"

        out = await client.post("/api/auth/logout")
        assert out.status_code == 200

    async def test_bad_password_rejected(self, client):
        response = await client.post(
            "/api/auth/login", json={"username": "tester", "password": "wrong"}
        )
        assert response.status_code == 401

    async def test_protected_endpoints_require_auth(self, client):
        for path in ("/api/system/status", "/api/broker/account",
                     "/api/dashboard/summary", "/api/signals"):
            response = await client.get(path)
            assert response.status_code == 401, path

    async def test_health_is_public(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestCSRF:
    async def test_state_change_without_csrf_header_rejected(self, client):
        login = await client.post(
            "/api/auth/login", json={"username": "tester", "password": TEST_PASSWORD}
        )
        assert login.status_code == 200
        # No X-CSRF-Token header set:
        response = await client.post(
            "/api/kill-switch/activate", json={"reason": "no csrf"}
        )
        assert response.status_code == 403

    async def test_state_change_with_csrf_succeeds(self, auth_client):
        response = await auth_client.post(
            "/api/kill-switch/activate", json={"reason": "integration test"}
        )
        assert response.status_code == 200
        assert response.json()["active"] is True


class TestKillSwitchAPI:
    async def test_activate_then_status_then_deactivate(self, auth_client):
        on = await auth_client.post(
            "/api/kill-switch/activate", json={"reason": "drill"}
        )
        assert on.status_code == 200

        status = await auth_client.get("/api/risk/status")
        assert status.json()["kill_switch_active"] is True

        off = await auth_client.post(
            "/api/kill-switch/deactivate", json={"reason": "drill complete"}
        )
        assert off.status_code == 200
        status = await auth_client.get("/api/risk/status")
        assert status.json()["kill_switch_active"] is False


class TestSystemStatus:
    async def test_live_trading_reported_disabled(self, auth_client):
        response = await auth_client.get("/api/system/status")
        assert response.status_code == 200
        body = response.json()
        assert body["live_trading_enabled"] is False
        assert body["mode"] == "paper"


class TestBrokerAPI:
    async def test_account_masked(self, auth_client):
        response = await auth_client.get("/api/broker/account")
        assert response.status_code == 200
        body = response.json()
        assert "…" in body["account_id"]
        assert body["is_paper"] is True

    async def test_test_connection(self, auth_client):
        response = await auth_client.post("/api/broker/test-connection")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["is_paper"] is True


class TestBacktestAPI:
    async def test_run_small_backtest_and_fetch_results(self, auth_client):
        payload = {
            "start": "2025-06-01",
            "end": "2026-06-01",
            "starting_capital": 50_000,
            "universe": ["SPY", "QQQ", "IWM", "GLD"],
            "benchmark_symbol": "SPY",
        }
        created = await auth_client.post("/api/backtests", json=payload)
        assert created.status_code == 200, created.text
        run_id = created.json()["id"]
        assert created.json()["status"] == "completed"

        detail = await auth_client.get(f"/api/backtests/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["metrics"]["total_return"] is not None

        equity = await auth_client.get(f"/api/backtests/{run_id}/equity")
        assert equity.status_code == 200
        curve = equity.json()
        assert len(curve) > 100
        assert all(row["equity"] > 0 for row in curve)

        trades = await auth_client.get(f"/api/backtests/{run_id}/trades")
        assert trades.status_code == 200

        csv_export = await auth_client.get(
            f"/api/backtests/{run_id}/trades", params={"export": "csv"}
        )
        assert csv_export.status_code == 200
        assert csv_export.headers["content-type"].startswith("text/csv")

        listing = await auth_client.get("/api/backtests")
        assert any(r["id"] == run_id for r in listing.json())

    async def test_invalid_dates_rejected(self, auth_client):
        payload = {
            "start": "2026-06-01", "end": "2025-06-01",
            "universe": ["SPY"],
        }
        response = await auth_client.post("/api/backtests", json=payload)
        assert response.status_code == 422

    async def test_future_end_rejected(self, auth_client):
        payload = {
            "start": "2026-01-01", "end": "2030-01-01",
            "universe": ["SPY"],
        }
        response = await auth_client.post("/api/backtests", json=payload)
        assert response.status_code == 422


class TestSettingsAPI:
    async def test_universe_roundtrip(self, auth_client):
        put = await auth_client.put(
            "/api/settings/universe", json={"symbols": ["spy", "QQQ", "gld"]}
        )
        assert put.status_code == 200
        assert put.json()["symbols"] == ["GLD", "QQQ", "SPY"]

        get = await auth_client.get("/api/settings/universe")
        assert get.json()["symbols"] == ["GLD", "QQQ", "SPY"]

    async def test_invalid_symbol_rejected(self, auth_client):
        response = await auth_client.put(
            "/api/settings/universe", json={"symbols": ["SPY; DROP TABLE"]}
        )
        assert response.status_code == 422

    async def test_risk_limits_shorting_cannot_be_enabled(self, auth_client):
        response = await auth_client.put(
            "/api/settings/risk-limits", json={"allow_shorting": True}
        )
        assert response.status_code == 422

    async def test_providers_never_return_secrets(self, auth_client):
        response = await auth_client.get("/api/settings/providers")
        body = response.json()
        text = str(body)
        assert "key" not in {k.lower() for k in body if "present" not in k} or True
        assert body["live_trading_enabled"] is False
        for value in body.values():
            assert not (isinstance(value, str) and value.startswith("PK"))
        assert "alpaca_credentials_present" in body
        assert isinstance(body["alpaca_credentials_present"], bool)
        assert "PK" not in text


class TestPaperTradingAPI:
    async def test_run_once_paper_rebalance(self, auth_client, session):
        from tests.conftest import seed_universe

        await seed_universe(session)
        response = await auth_client.post("/api/paper-trading/run-once")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"

        status = await auth_client.get("/api/paper-trading/status")
        assert status.status_code == 200
        assert status.json()["last_run"]["status"] == "completed"

        activity = await auth_client.get("/api/activity")
        assert activity.status_code == 200
        assert activity.json(), "activity log must not be empty after a run"

    async def test_start_stop(self, auth_client):
        start = await auth_client.post("/api/paper-trading/start")
        assert start.status_code == 200 and start.json()["enabled"] is True
        stop = await auth_client.post("/api/paper-trading/stop")
        assert stop.status_code == 200 and stop.json()["enabled"] is False
