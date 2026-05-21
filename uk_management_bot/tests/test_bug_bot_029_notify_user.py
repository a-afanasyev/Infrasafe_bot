"""
BUG-BOT-029: `ShiftTransferService.process_expired_transfers` вызывал
несуществующий `NotificationService.notify_user`, что приводило к
`AttributeError` в логах (без падения главного пути).

После фикса: `NotificationService.notify_user(user_id, title, message)`
существует и вызывает `send_to_user(bot, telegram_id, text)`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestBugBot029NotifyUser:
    def test_method_exists(self) -> None:
        """`NotificationService.notify_user` присутствует с ожидаемой сигнатурой."""
        from uk_management_bot.services.notification_service import NotificationService

        assert hasattr(NotificationService, "notify_user")
        # Проверяем сигнатуру: self, user_id, title, message
        import inspect
        sig = inspect.signature(NotificationService.notify_user)
        params = list(sig.parameters.keys())
        assert params == ["self", "user_id", "title", "message"]

    def test_notify_user_skips_missing_user(self) -> None:
        """Если user_id не найден в БД — warning, без исключения."""
        from uk_management_bot.services.notification_service import NotificationService

        db = MagicMock()
        # query().filter().first() возвращает None
        db.query.return_value.filter.return_value.first.return_value = None

        svc = NotificationService(db=db, bot=MagicMock())
        # Не бросает
        result = svc.notify_user(user_id=999, title="t", message="m")
        assert result is None

    def test_notify_user_sends_to_telegram_id(self) -> None:
        """Если user найден — отправка идёт через send_to_user(bot, telegram_id, text)."""
        from uk_management_bot.services.notification_service import NotificationService

        user = MagicMock()
        user.id = 1
        user.telegram_id = 555

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        bot = MagicMock()
        svc = NotificationService(db=db, bot=bot)

        with patch(
            "uk_management_bot.services.notification_service.send_to_user"
        ) as mock_send:
            svc.notify_user(user_id=1, title="Hello", message="World")

        mock_send.assert_called_once()
        args = mock_send.call_args.args
        assert args[0] is bot
        assert args[1] == 555
        assert "Hello" in args[2] and "World" in args[2]

    def test_shift_transfer_service_uses_existing_method(self) -> None:
        """`ShiftTransferService` обращается к `notify_user`, а метод теперь существует."""
        from uk_management_bot.services.notification_service import NotificationService
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        # Простая проверка контрактов
        assert callable(getattr(NotificationService, "notify_user", None))
        svc = ShiftTransferService(db=MagicMock())
        assert hasattr(svc.notification_service, "notify_user")
