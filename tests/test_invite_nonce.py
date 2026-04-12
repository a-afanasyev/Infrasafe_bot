"""
Tests for InviteNonce model and atomic nonce deduplication in InviteService.

Verifies that:
- _use_nonce_atomically() prevents double-use via UNIQUE constraint
- _is_nonce_used() does exact match (no LIKE wildcards)
- mark_nonce_used() public wrapper delegates to atomic path
- validate_invite(mark_used_by=...) consumes the nonce in one step
"""
import pytest
import json
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.invite_nonce import InviteNonce
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.invite_service import InviteService


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def invite_service(db_session):
    """InviteService with a test HMAC secret."""
    with patch("uk_management_bot.services.invite_service.settings") as mock_settings:
        mock_settings.INVITE_SECRET = "test_secret_key_for_testing_purposes_only"
        yield InviteService(db_session)


class TestInviteNonceModel:
    """Tests for the InviteNonce SQLAlchemy model."""

    def test_create_nonce_record(self, db_session):
        record = InviteNonce(nonce="abc123", used_by=42, invite_payload={"role": "applicant"})
        db_session.add(record)
        db_session.commit()

        fetched = db_session.query(InviteNonce).filter_by(nonce="abc123").one()
        assert fetched.used_by == 42
        assert fetched.invite_payload["role"] == "applicant"
        assert fetched.used_at is not None

    def test_unique_constraint_prevents_duplicate(self, db_session):
        """Inserting the same nonce twice must raise IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        db_session.add(InviteNonce(nonce="dup_nonce", used_by=1))
        db_session.commit()

        db_session.add(InviteNonce(nonce="dup_nonce", used_by=2))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_repr(self, db_session):
        record = InviteNonce(nonce="abcdefghijklmnop", used_by=7)
        assert "abcdefgh" in repr(record)


class TestAtomicNonceUsage:
    """Tests for _use_nonce_atomically and _is_nonce_used."""

    def test_use_nonce_atomically_succeeds_first_time(self, invite_service, db_session):
        invite_service._use_nonce_atomically(
            "fresh_nonce", 100, {"role": "applicant", "created_by": 1}
        )
        db_session.commit()

        record = db_session.query(InviteNonce).filter_by(nonce="fresh_nonce").one()
        assert record.used_by == 100
        assert record.invite_payload["role"] == "applicant"

    def test_use_nonce_atomically_rejects_duplicate(self, invite_service, db_session):
        invite_service._use_nonce_atomically(
            "once_nonce", 100, {"role": "applicant", "created_by": 1}
        )
        db_session.commit()

        with pytest.raises(ValueError, match="Token already used"):
            invite_service._use_nonce_atomically(
                "once_nonce", 200, {"role": "manager", "created_by": 2}
            )

    def test_use_nonce_atomically_writes_audit_log(self, invite_service, db_session):
        invite_service._use_nonce_atomically(
            "audit_nonce", 300, {"role": "executor", "created_by": 5, "specialization": "plumber"}
        )
        db_session.commit()

        audit = db_session.query(AuditLog).filter_by(action="invite_used").first()
        assert audit is not None
        details = json.loads(audit.details)
        assert details["nonce"] == "audit_nonce"
        assert details["specialization"] == "plumber"

    def test_is_nonce_used_false_for_fresh(self, invite_service):
        assert invite_service._is_nonce_used("never_seen") is False

    def test_is_nonce_used_true_after_atomic_use(self, invite_service, db_session):
        invite_service._use_nonce_atomically(
            "used_nonce", 100, {"role": "applicant", "created_by": 1}
        )
        db_session.commit()
        assert invite_service._is_nonce_used("used_nonce") is True

    def test_is_nonce_used_exact_match_no_wildcards(self, invite_service, db_session):
        """Underscore in nonce must NOT match other nonces (no LIKE wildcards)."""
        invite_service._use_nonce_atomically(
            "a_b", 100, {"role": "applicant", "created_by": 1}
        )
        db_session.commit()

        # 'a_b' should match itself
        assert invite_service._is_nonce_used("a_b") is True
        # 'aXb' should NOT match (would match if LIKE '%a_b%' was used)
        assert invite_service._is_nonce_used("aXb") is False
        # 'axb' also should NOT match
        assert invite_service._is_nonce_used("axb") is False


class TestValidateInviteAtomicPath:
    """Tests for validate_invite with mark_used_by."""

    def test_validate_and_mark_atomically(self, invite_service, db_session):
        token = invite_service.generate_invite(role="applicant", created_by=1)
        payload = invite_service.validate_invite(token, mark_used_by=42)
        db_session.commit()

        assert payload["role"] == "applicant"
        # Nonce should now be consumed
        assert invite_service._is_nonce_used(payload["nonce"]) is True

    def test_validate_same_token_twice_fails(self, invite_service, db_session):
        token = invite_service.generate_invite(role="applicant", created_by=1)
        invite_service.validate_invite(token, mark_used_by=42)
        db_session.commit()

        with pytest.raises(ValueError, match="Token already used"):
            invite_service.validate_invite(token, mark_used_by=99)

    def test_validate_without_mark_checks_nonce(self, invite_service, db_session):
        """validate_invite without mark_used_by should still detect used nonces."""
        token = invite_service.generate_invite(role="manager", created_by=1)
        invite_service.validate_invite(token, mark_used_by=10)
        db_session.commit()

        with pytest.raises(ValueError, match="Token already used"):
            invite_service.validate_invite(token)

    def test_validate_without_mark_passes_for_fresh_token(self, invite_service):
        token = invite_service.generate_invite(role="applicant", created_by=1)
        payload = invite_service.validate_invite(token)
        assert payload["role"] == "applicant"


class TestMarkNonceUsedWrapper:
    """Tests for the public mark_nonce_used backward-compat wrapper."""

    def test_mark_nonce_used_delegates_to_atomic(self, invite_service, db_session):
        invite_service.mark_nonce_used("wrapper_nonce", 55, {"role": "applicant", "created_by": 1})
        db_session.commit()

        record = db_session.query(InviteNonce).filter_by(nonce="wrapper_nonce").one()
        assert record.used_by == 55

    def test_mark_nonce_used_rejects_duplicate(self, invite_service, db_session):
        invite_service.mark_nonce_used("dup_wrap", 55, {"role": "applicant", "created_by": 1})
        db_session.commit()

        with pytest.raises(ValueError, match="Token already used"):
            invite_service.mark_nonce_used("dup_wrap", 66, {"role": "manager", "created_by": 2})
