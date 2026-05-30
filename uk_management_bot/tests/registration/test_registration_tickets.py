import pytest
from uk_management_bot.api.registration.tickets import (
    create_registration_ticket, verify_registration_ticket,
)


@pytest.mark.unit
def test_roundtrip_returns_telegram_id():
    tok = create_registration_ticket(123456789)
    assert verify_registration_ticket(tok) == 123456789


@pytest.mark.unit
def test_rejects_garbage():
    assert verify_registration_ticket("not-a-jwt") is None


@pytest.mark.unit
def test_rejects_mfa_token():
    from uk_management_bot.api.auth.service import create_mfa_token
    assert verify_registration_ticket(create_mfa_token(5)) is None
