"""
Unit tests for InviteService (mock-based, no DB required).

Covers:
- generate_invite (happy path, invalid role, missing specialization)
- generate_invite_link
- validate_invite (happy path, expired, bad format, bad signature, used nonce)
- validate_invite_token (valid, invalid)
- is_nonce_used / mark_nonce_used
- join_via_invite
"""
import pytest
import json
import time
import base64
import hmac
import hashlib
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta


def _build_service(db_mock, invite_secret="test_secret_123"):
    """Build InviteService with mocked settings."""
    with patch("uk_management_bot.services.invite_service.settings") as mock_settings:
        mock_settings.INVITE_SECRET = invite_secret
        mock_settings.BOT_USERNAME = "testbot"
        from uk_management_bot.services.invite_service import InviteService
        return InviteService(db_mock)


# ===== generate_invite =====

class TestGenerateInvite:
    def setup_method(self):
        self.db = MagicMock()
        # Mock audit log methods
        self.db.query.return_value.filter.return_value.first.return_value = None
        self.svc = _build_service(self.db)

    def test_generates_token_for_applicant(self):
        token = self.svc.generate_invite("applicant", created_by=100)
        assert token.startswith("invite_v1:")
        assert "." in token

    def test_generates_token_for_executor_with_spec(self):
        token = self.svc.generate_invite("executor", created_by=100, specialization="electricity")
        assert token.startswith("invite_v1:")

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            self.svc.generate_invite("invalid_role", created_by=100)

    def test_executor_without_specialization_raises(self):
        with pytest.raises(ValueError, match="Specialization is required"):
            self.svc.generate_invite("executor", created_by=100)

    def test_token_roundtrip(self):
        """Generate a token, then validate it."""
        with patch.object(self.svc, "is_nonce_used", return_value=False):
            token = self.svc.generate_invite("applicant", created_by=100, hours=24)
            payload = self.svc.validate_invite(token)
            assert payload["role"] == "applicant"
            assert payload["created_by"] == 100


# ===== generate_invite_link =====

class TestGenerateInviteLink:
    def setup_method(self):
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.first.return_value = None
        self.svc = _build_service(self.db)

    def test_returns_bot_link(self):
        link = self.svc.generate_invite_link("applicant", created_by=100)
        assert "t.me/" in link


# ===== validate_invite =====

class TestValidateInvite:
    def setup_method(self):
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.first.return_value = None
        self.svc = _build_service(self.db)

    def test_valid_token(self):
        with patch.object(self.svc, "is_nonce_used", return_value=False):
            token = self.svc.generate_invite("manager", created_by=100)
            payload = self.svc.validate_invite(token)
            assert payload["role"] == "manager"

    def test_expired_token_raises(self):
        with patch.object(self.svc, "is_nonce_used", return_value=False):
            # Generate a token with 0 hours = already expired
            token = self.svc.generate_invite("applicant", created_by=100, hours=0)
            # Need to wait a moment for it to be expired, or set expires_at in the past
            # Instead, let's manually build an expired token
            payload = {
                "role": "applicant",
                "expires_at": int(time.time()) - 3600,  # 1 hour ago
                "nonce": "test-nonce-123",
                "created_by": 100,
            }
            payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
            signature = hmac.new(
                self.svc.secret, payload_b64.encode(), hashlib.sha256
            ).hexdigest()
            expired_token = f"invite_v1:{payload_b64}.{signature}"

            with pytest.raises(ValueError, match="expired"):
                self.svc.validate_invite(expired_token)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="format"):
            self.svc.validate_invite("not_a_valid_token")

    def test_no_dot_raises(self):
        with pytest.raises(ValueError, match="structure"):
            self.svc.validate_invite("invite_v1:nodothere")

    def test_bad_signature_raises(self):
        token = self.svc.generate_invite("applicant", created_by=100)
        # Corrupt the signature
        parts = token.rsplit(".", 1)
        bad_token = parts[0] + ".0000000000000000"
        with pytest.raises(ValueError, match="signature"):
            self.svc.validate_invite(bad_token)

    def test_used_nonce_raises(self):
        with patch.object(self.svc, "is_nonce_used", return_value=True):
            token = self.svc.generate_invite("applicant", created_by=100)
            with pytest.raises(ValueError, match="already used"):
                self.svc.validate_invite(token)

    def test_mark_used_by_calls_mark_nonce(self):
        with patch.object(self.svc, "is_nonce_used", return_value=False), \
             patch.object(self.svc, "mark_nonce_used") as mock_mark:
            token = self.svc.generate_invite("applicant", created_by=100)
            self.svc.validate_invite(token, mark_used_by=200)
            mock_mark.assert_called_once()


# ===== validate_invite_token =====

class TestValidateInviteToken:
    def setup_method(self):
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.first.return_value = None
        self.svc = _build_service(self.db)

    def test_valid_returns_valid_dict(self):
        with patch.object(self.svc, "is_nonce_used", return_value=False):
            token = self.svc.generate_invite("applicant", created_by=100)
            result = self.svc.validate_invite_token(token)
            assert result["valid"] is True
            assert result["invite_data"]["role"] == "applicant"

    def test_invalid_returns_invalid_dict(self):
        result = self.svc.validate_invite_token("bad_token")
        assert result["valid"] is False


# ===== is_nonce_used =====

class TestIsNonceUsed:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_unused_nonce(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        assert self.svc.is_nonce_used("unused-nonce") is False

    def test_used_nonce(self):
        self.db.query.return_value.filter.return_value.first.return_value = MagicMock()
        assert self.svc.is_nonce_used("used-nonce") is True

    def test_exception_returns_true(self):
        """On exception, assume nonce is used for safety."""
        self.db.query.side_effect = Exception("DB error")
        assert self.svc.is_nonce_used("error-nonce") is True


# ===== mark_nonce_used =====

class TestMarkNonceUsed:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_creates_audit_log(self):
        self.db.query.return_value.filter.return_value.first.return_value = None  # user not found
        self.svc.mark_nonce_used("test-nonce", 100, {"role": "applicant", "created_by": 50})
        self.db.add.assert_called_once()
        self.db.commit.assert_called_once()

    def test_exception_raises(self):
        self.db.add.side_effect = Exception("fail")
        with pytest.raises(Exception):
            self.svc.mark_nonce_used("test-nonce", 100, {"role": "applicant", "created_by": 50})
        self.db.rollback.assert_called()


# ===== InviteService.__init__ =====

class TestInviteServiceInit:
    def test_missing_secret_raises(self):
        with patch("uk_management_bot.services.invite_service.settings") as mock_settings:
            mock_settings.INVITE_SECRET = None
            with pytest.raises(ValueError, match="INVITE_SECRET"):
                from uk_management_bot.services.invite_service import InviteService
                InviteService(MagicMock())


# ===== join_via_invite =====

class TestJoinViaInvite:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_existing_user_returns_failure(self):
        existing_user = MagicMock()
        with patch.object(self.svc, "validate_invite", return_value={"role": "applicant", "nonce": "n"}):
            # self.db.query(User).filter(...).first() returns existing user
            self.db.query.return_value.filter.return_value.first.return_value = existing_user
            result = self.svc.join_via_invite("token", 100)
            assert result["success"] is False
            assert "уже зарегистрирован" in result["message"]

    def test_invalid_token_returns_failure(self):
        with patch.object(self.svc, "validate_invite", side_effect=ValueError("Token expired")):
            result = self.svc.join_via_invite("bad_token", 100)
            assert result["success"] is False
            assert "expired" in result["message"]
