"""BUG-146 — notification_service: markdown в raw-отправке, RU-хардкод
документов, send_to_channel без признака доставки, мёртвый old_role.

1. Билдеры documents.py слали `**…**`, а отправка идёт без parse_mode —
   пользователь видел буквальные звёздочки.
2. Словари document_names были захардкожены по-русски — user.language
   игнорировался (UZ-пользователь получал русские названия).
3. `send_to_channel` не возвращал признак доставки (BUG-BOT-036 был закрыт
   только для send_to_user), лог send_manager_notification писал «канал=on»
   по конфигу, а не по факту доставки.
4. Неиспользуемый параметр `old_role` в async_notify_role_switched удалён.
"""
import inspect
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.services.notification_service.channel import send_to_channel
from uk_management_bot.services.notification_service.documents import (
    build_document_request_message,
    build_multiple_documents_request_message,
)
from uk_management_bot.services.notification_service.requests_roles import (
    async_notify_role_switched,
)
from uk_management_bot.services.notification_service.service import (
    NotificationService,
)
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT


def _user(language: str = "ru", telegram_id: int = 100) -> SimpleNamespace:
    return SimpleNamespace(telegram_id=telegram_id, language=language)


# ---------------------------------------------------------------------------
# 1. Билдеры без markdown-разметки (отправка raw, parse_mode нет)
# ---------------------------------------------------------------------------

class TestBuildersNoMarkdown:
    def test_single_document_message_has_no_markdown(self):
        msg = build_document_request_message(_user(), "Загрузите", "passport")
        assert "**" not in msg

    def test_multiple_documents_message_has_no_markdown(self):
        msg = build_multiple_documents_request_message(
            _user(), "Загрузите всё", ["passport", "rental_agreement"]
        )
        assert "**" not in msg


# ---------------------------------------------------------------------------
# 2. Локализация названий документов по user.language
# ---------------------------------------------------------------------------

class TestDocumentNamesLocalized:
    def test_uz_user_gets_uzbek_document_name(self):
        msg = build_document_request_message(_user(language="uz"), "Yuklang", "passport")
        assert "pasport" in msg
        assert "паспорт" not in msg

    def test_ru_user_gets_russian_document_name(self):
        msg = build_document_request_message(_user(language="ru"), "Загрузите", "passport")
        assert "паспорт" in msg

    def test_uz_user_gets_uzbek_names_in_multiple(self):
        msg = build_multiple_documents_request_message(
            _user(language="uz"), "Yuklang", ["property_deed", "utility_bill"]
        )
        assert "mulk guvohnomasi" in msg
        assert "kommunal to'lov kvitansiyasi" in msg

    def test_missing_language_falls_back_to_ru(self):
        user = SimpleNamespace(telegram_id=1, language=None)
        msg = build_document_request_message(user, "Загрузите", "rental_agreement")
        assert "договор аренды" in msg


# ---------------------------------------------------------------------------
# 3. send_to_channel возвращает bool (по образцу send_to_user, BUG-BOT-036)
# ---------------------------------------------------------------------------

class TestSendToChannelReturnsBool:
    async def test_returns_true_on_delivery(self):
        bot = AsyncMock()
        with patch(
            "uk_management_bot.services.notification_service.channel.settings"
        ) as mock_settings:
            mock_settings.TELEGRAM_CHANNEL_ID = "-100123"
            assert await send_to_channel(bot, "text") is True
        bot.send_message.assert_called_once_with(
            "-100123", "text", request_timeout=SEND_TIMEOUT
        )

    async def test_returns_false_when_channel_not_configured(self):
        bot = AsyncMock()
        with patch(
            "uk_management_bot.services.notification_service.channel.settings"
        ) as mock_settings:
            mock_settings.TELEGRAM_CHANNEL_ID = None
            assert await send_to_channel(bot, "text") is False
        bot.send_message.assert_not_called()

    async def test_returns_false_on_bot_exception(self):
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Forbidden")
        with patch(
            "uk_management_bot.services.notification_service.channel.settings"
        ) as mock_settings:
            mock_settings.TELEGRAM_CHANNEL_ID = "-100123"
            assert await send_to_channel(bot, "text") is False


class TestManagerNotificationHonestChannelLog:
    def _svc(self):
        return NotificationService(MagicMock(), bot=AsyncMock())

    async def _run(self, delivered: bool, caplog):
        svc = self._svc()
        with patch(
            "uk_management_bot.services.feedback_service.manager_telegram_ids_sync",
            return_value=[],
        ), patch(
            "uk_management_bot.services.notification_service.service.send_to_channel",
            new_callable=AsyncMock, return_value=delivered,
        ):
            with caplog.at_level(
                logging.INFO,
                logger="uk_management_bot.services.notification_service.service",
            ):
                await svc.send_manager_notification("T", "B")
        return caplog.text

    async def test_channel_on_only_when_actually_delivered(self, caplog):
        text = await self._run(True, caplog)
        assert "канал=on" in text

    async def test_channel_off_when_delivery_failed(self, caplog):
        """Раньше лог писал «канал=on» по конфигу даже при недоставке."""
        text = await self._run(False, caplog)
        assert "канал=off" in text
        assert "канал=on" not in text


# ---------------------------------------------------------------------------
# 4. async_notify_role_switched: мёртвый параметр old_role удалён
# ---------------------------------------------------------------------------

class TestRoleSwitchedSignature:
    def test_old_role_param_removed(self):
        params = inspect.signature(async_notify_role_switched).parameters
        assert "old_role" not in params
        assert list(params) == ["bot", "db", "user", "new_role"]

    async def test_sends_localized_text_to_user(self):
        bot = AsyncMock()
        db = MagicMock()
        user = _user(telegram_id=123)
        with patch(
            "uk_management_bot.services.notification_service.requests_roles.send_to_user",
            new_callable=AsyncMock,
        ) as mock_send:
            await async_notify_role_switched(bot, db, user, "executor")
        mock_send.assert_called_once()
        assert mock_send.call_args.args[1] == 123
