"""
BUG-BOT-016: `TELEGRAM_CHANNEL_ID=@your_notifications_channel` placeholder в .env
вызывал WARNING при каждом старте бота.

После фикса: `_resolve_channel_id()` возвращает None если значение пустое
или равно одному из placeholder-значений.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from uk_management_bot.services import notification_service


class TestBugBot016ChannelIdPlaceholder:
    @pytest.mark.parametrize("placeholder", [
        "@your_notifications_channel",
        "your_notifications_channel",
        "your_channel_id",
        "@your_channel",
        "",
        "   ",
        None,
    ])
    def test_placeholder_resolves_to_none(self, placeholder) -> None:
        with patch.object(notification_service.settings, "TELEGRAM_CHANNEL_ID", placeholder):
            assert notification_service._resolve_channel_id() is None

    @pytest.mark.parametrize("real_value,expected", [
        ("-1001234567890", "-1001234567890"),
        ("@uk_notifications", "@uk_notifications"),
        ("  -1009876543210  ", "-1009876543210"),
    ])
    def test_real_channel_id_passes_through(self, real_value: str, expected: str) -> None:
        with patch.object(notification_service.settings, "TELEGRAM_CHANNEL_ID", real_value):
            assert notification_service._resolve_channel_id() == expected

    async def test_send_to_channel_silent_when_placeholder(self) -> None:
        """Не должно быть исключений или вызовов bot.send_message с placeholder."""
        class FakeBot:
            called = False

            async def send_message(self, *args, **kwargs):  # pragma: no cover - не должна быть вызвана
                FakeBot.called = True

        bot = FakeBot()
        with patch.object(notification_service.settings, "TELEGRAM_CHANNEL_ID", "@your_notifications_channel"):
            await notification_service.send_to_channel(bot, "test")
        assert FakeBot.called is False
