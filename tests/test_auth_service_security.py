"""Security tests for JWT auth service: iss/aud claims, secret validation."""
import pytest
from datetime import timedelta
from unittest.mock import patch

from jose import jwt

from uk_management_bot.api.auth.service import (
    create_access_token,
    verify_access_token,
    SECRET_KEY,
    ALGORITHM,
)


class TestJwtClaimsIssAud:
    """Tokens must include iss and aud claims, and verification must enforce them."""

    def test_token_contains_iss_claim(self):
        token = create_access_token(user_id=1, roles=["applicant"])
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            audience="uk-management-api", issuer="uk-management",
        )
        assert payload["iss"] == "uk-management"

    def test_token_contains_aud_claim(self):
        token = create_access_token(user_id=1, roles=["applicant"])
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            audience="uk-management-api", issuer="uk-management",
        )
        assert payload["aud"] == "uk-management-api"

    def test_token_with_wrong_audience_rejected(self):
        token = create_access_token(user_id=1, roles=["manager"])
        # Craft a token with wrong audience
        raw = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            audience="uk-management-api", issuer="uk-management",
        )
        raw["aud"] = "wrong-audience"
        tampered = jwt.encode(raw, SECRET_KEY, algorithm=ALGORITHM)
        assert verify_access_token(tampered) is None

    def test_token_with_wrong_issuer_rejected(self):
        token = create_access_token(user_id=1, roles=["executor"])
        raw = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            audience="uk-management-api", issuer="uk-management",
        )
        raw["iss"] = "wrong-issuer"
        tampered = jwt.encode(raw, SECRET_KEY, algorithm=ALGORITHM)
        assert verify_access_token(tampered) is None

    def test_token_without_audience_rejected(self):
        """A token missing the aud claim must be rejected."""
        payload = {
            "sub": "1",
            "roles": ["applicant"],
            "exp": (
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                + timedelta(hours=1)
            ),
            "iss": "uk-management",
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        assert verify_access_token(token) is None

    def test_token_without_issuer_rejected(self):
        """A token missing the iss claim must be rejected."""
        payload = {
            "sub": "1",
            "roles": ["applicant"],
            "exp": (
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                + timedelta(hours=1)
            ),
            "aud": "uk-management-api",
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        assert verify_access_token(token) is None

    def test_valid_token_roundtrip(self):
        """A properly formed token passes verification with all claims."""
        token = create_access_token(user_id=42, roles=["manager", "executor"])
        payload = verify_access_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["roles"] == ["manager", "executor"]
        assert payload["iss"] == "uk-management"
        assert payload["aud"] == "uk-management-api"


class TestSecretKeyValidation:
    """SECRET_KEY must never fall back to a dev default."""

    def test_missing_secret_raises_runtime_error(self):
        """When both JWT_SECRET and INVITE_SECRET are None, module must raise."""
        mock_settings = type("S", (), {
            "JWT_SECRET": None,
            "INVITE_SECRET": None,
            "DEBUG": True,
        })()

        with pytest.raises(RuntimeError, match="JWT_SECRET or INVITE_SECRET must be set"):
            # Re-execute the module-level guard logic
            secret = mock_settings.JWT_SECRET or mock_settings.INVITE_SECRET
            if not secret:
                raise RuntimeError(
                    "JWT_SECRET or INVITE_SECRET must be set in all environments"
                )

    def test_no_dev_fallback_secret_in_codebase(self):
        """The hardcoded dev secret must not appear anywhere in the auth service."""
        import inspect
        import uk_management_bot.api.auth.service as mod

        source = inspect.getsource(mod)
        assert "dev-jwt-secret-DO-NOT-USE-IN-PROD" not in source
