"""Security utility tests: password hashing, session tokens, reconciliation."""

from __future__ import annotations

from app.utils.security import (
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)

SECRET = "test-secret"


class TestPasswords:
    def test_roundtrip(self):
        stored = hash_password("s3cret!")
        assert verify_password("s3cret!", stored)
        assert not verify_password("wrong", stored)

    def test_unique_salts(self):
        assert hash_password("same") != hash_password("same")

    def test_garbage_hash_fails_closed(self):
        assert not verify_password("x", "not-a-real-hash")
        assert not verify_password("x", "")


class TestSessionTokens:
    def test_roundtrip(self):
        token, csrf = create_session_token("alice", SECRET, ttl_minutes=10)
        payload = verify_session_token(token, SECRET)
        assert payload is not None
        assert payload["sub"] == "alice"
        assert payload["csrf"] == csrf

    def test_tampered_token_rejected(self):
        token, _ = create_session_token("alice", SECRET, 10)
        assert verify_session_token(token + "x", SECRET) is None
        assert verify_session_token("garbage", SECRET) is None

    def test_wrong_secret_rejected(self):
        token, _ = create_session_token("alice", SECRET, 10)
        assert verify_session_token(token, "other-secret") is None

    def test_expired_token_rejected(self):
        token, _ = create_session_token("alice", SECRET, ttl_minutes=-1)
        assert verify_session_token(token, SECRET) is None


class TestReconciliation:
    async def test_matching_state_reconciles(self, session, mock_broker):
        from app.services.execution.reconciliation import (
            reconcile,
            sync_positions_from_broker,
        )

        await sync_positions_from_broker(session, mock_broker)
        report = await reconcile(session, mock_broker)
        assert report.matched

    async def test_mismatch_detected(self, session, mock_broker):
        from app.models.trading import PositionRecord
        from app.services.execution.reconciliation import reconcile
        from app.utils.timeutils import utcnow

        session.add(
            PositionRecord(
                symbol="SPY", quantity=42, avg_entry_price=400.0,
                as_of=utcnow(), is_current=True,
            )
        )
        await session.flush()
        report = await reconcile(session, mock_broker)
        assert not report.matched
        types = {d["type"] for d in report.discrepancies}
        assert "position_missing_at_broker" in types
