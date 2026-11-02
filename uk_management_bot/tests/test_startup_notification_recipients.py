"""Уведомление о запуске/перезапуске бота — только администраторам.

Решение владельца 2026-11-03: при перезапуске бота жителям и менеджерам ничего
не уходит, только `ADMIN_USER_IDS` (+ служебный ops-канал, если задан). Пин
против «удобного» расширения рассылки на всех пользователей из БД.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", [None, "-100777"])
async def test_startup_notification_goes_to_admins_only(monkeypatch, channel):
    import uk_management_bot.main as main_mod

    monkeypatch.setattr(main_mod.settings, "ADMIN_USER_IDS", [111, 222])
    bot = MagicMock()
    bot.send_message = AsyncMock()
    with patch.object(main_mod, "get_scheduler_status",
                      new=AsyncMock(return_value={"is_running": False, "jobs_count": 0})), \
         patch("uk_management_bot.services.notification_service._resolve_channel_id",
               return_value=channel):
        await main_mod.send_startup_notification(bot)

    recipients = [c.args[0] for c in bot.send_message.await_args_list]
    expected = [111, 222] + ([channel] if channel else [])
    assert recipients == expected
