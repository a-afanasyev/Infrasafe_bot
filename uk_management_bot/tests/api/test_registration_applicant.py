import pytest
from unittest.mock import AsyncMock, patch
from uk_management_bot.api.registration.notify import notify_managers_new_registration


@pytest.mark.asyncio
async def test_notify_swallows_errors(monkeypatch):
    monkeypatch.setattr("uk_management_bot.config.settings.settings.ADMIN_USER_IDS", [111])
    with patch("uk_management_bot.api.registration.notify._send", new=AsyncMock(side_effect=Exception("boom"))):
        # must NOT raise
        await notify_managers_new_registration(telegram_id=5, full_name="Иван", apartment_label="Двор-1, кв 12")
