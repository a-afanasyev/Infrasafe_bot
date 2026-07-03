"""API lifespan: регистрация и закрытие shared notification bot (COD-03).

Обычные API-тесты гоняют httpx.ASGITransport, который НЕ прогоняет
startup/shutdown. Здесь используем fastapi.testclient.TestClient — он реально
запускает lifespan на входе/выходе `with`, что позволяет проверить, что бот
регистрируется на старте и его aiohttp-сессия закрывается + shared сбрасывается
на shutdown. Тяжёлые startup-петли и redis-проба запатчены для изоляции.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from uk_management_bot.config.settings import settings as app_settings


def test_lifespan_registers_and_closes_notification_bot():
    from uk_management_bot.api.main import app

    fake_bot = MagicMock()
    fake_bot.session.close = AsyncMock()

    rl_ok = AsyncMock(return_value={"configured_backend": "memory", "redis_reachable": True})

    with patch("uk_management_bot.api.lifecycle.rate_limit_backend_status", new=rl_ok), \
            patch.object(app_settings, "INFRASAFE_WEBHOOK_ENABLED", False), \
            patch("aiogram.Bot", return_value=fake_bot), \
            patch("uk_management_bot.services.notification_service.set_shared_bot") as mock_set:
        with TestClient(app):
            # startup выполнился → shared bot зарегистрирован фейковым ботом
            assert any(c.args == (fake_bot,) for c in mock_set.call_args_list), \
                "set_shared_bot(bot) должен быть вызван на startup"
        # выход из блока = shutdown → сессия закрыта + shared сброшен в None
        fake_bot.session.close.assert_awaited_once()
        assert mock_set.call_args_list[-1].args == (None,), \
            "на shutdown shared bot должен сбрасываться в None"
