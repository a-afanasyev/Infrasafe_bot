from datetime import timedelta
from uk_management_bot.api.auth.service import (
    create_access_token, verify_access_token,
    hash_password, verify_password,
    verify_twa_init_data,
)


def test_access_token_roundtrip():
    token = create_access_token(user_id=42, roles=["manager"])
    payload = verify_access_token(token)
    assert payload["sub"] == "42"
    assert payload["roles"] == ["manager"]


def test_expired_token_returns_none():
    token = create_access_token(user_id=1, roles=["applicant"], expires_delta=timedelta(seconds=-1))
    assert verify_access_token(token) is None


def test_password_hash_and_verify():
    hashed = hash_password("MySecret123")
    assert verify_password("MySecret123", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_verify_password_handles_malformed_hash():
    """A corrupted password_hash in DB (shell-escape strip, manual edit, bad
    seed migration) must produce a failed-credential result, NOT a 500 from
    leaked bcrypt ValueError. Found during INT-120 prod smoke 2026-05-25:
    psql -c with shell-escaped $ stripped the prefix, leaving "b2.WVBA..."
    instead of "$2b$12$Y4Xb.WVBA..." — login_password then 500'd on every
    attempt."""
    # No prefix → bcrypt raises ValueError("Invalid salt")
    assert verify_password("anything", "b2.WVBA.no.prefix") is False
    # Empty string → bcrypt raises ValueError
    assert verify_password("anything", "") is False
    # Random garbage
    assert verify_password("anything", "not-a-bcrypt-hash-at-all") is False


def test_twa_init_data_invalid_hash():
    result = verify_twa_init_data("user=%7B%22id%22%3A123%7D&hash=badhash", "fake_bot_token")
    assert result is None
