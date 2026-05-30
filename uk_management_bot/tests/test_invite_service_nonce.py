"""Service-level nonce tests for InviteService (SEC-020 TOCTOU).

Moved out of the now-retired web-endpoint test module
(`test_invite_sec020.py`) when the `uk_management_bot/web/` registration
service was removed. These tests exercise `InviteService` directly — no
FastAPI / web layer involved.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Service-level: typed exception is raised, not generic ValueError ──

def test_validate_invite_raises_token_already_used_error_on_race_loser():
    """The atomic INSERT path raises the typed exception (subclass of
    ValueError, so old try/except ValueError catchers still work)."""
    from uk_management_bot.services.invite_service import (
        TokenAlreadyUsedError,
    )
    from sqlalchemy.exc import IntegrityError

    # Build the service with a MagicMock'd db that throws IntegrityError on
    # flush — simulating the second concurrent INSERT losing to UNIQUE.
    with patch("uk_management_bot.services.invite_service.settings") as mock_settings:
        mock_settings.INVITE_SECRET = "test_secret_for_unit_tests"
        from uk_management_bot.services.invite_service import InviteService

        db = MagicMock()
        db.flush.side_effect = IntegrityError("INSERT", {}, Exception())
        svc = InviteService(db)

        with pytest.raises(TokenAlreadyUsedError, match="already used"):
            svc._use_nonce_atomically("test-nonce", 555, {"role": "applicant"})

    # And it's a ValueError subclass for back-compat with older catchers.
    assert issubclass(TokenAlreadyUsedError, ValueError)
