"""Подписчик резидентских уведомлений (access:resident_notify → Telegram).

Тестируется ЧИСТАЯ логика обработки одного сообщения (``handle_payload``) и
сборка локализованного текста (``build_notification_text``) — без живого Redis.
Контракт сообщения — ``access_control.services.resident_notify``.

PD-safe (§11): в канал кладётся только маскированный хвост номера; полный номер
тут не фигурирует. Доставка best-effort: сбой/неизвестный адресат не должны
ронять цикл.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from access_control.services.resident_notify import (
    KIND_DISPUTED_ENTRY,
    KIND_VEHICLE_REQUEST_RESOLVED,
)
from uk_management_bot.services.access_notify_subscriber import (
    build_notification_text,
    build_reply_markup,
    handle_payload,
    parse_payload,
)


def _db_with_user(telegram_id: int = 555, language: str = "ru"):
    """MagicMock-сессия: query(User).filter(...).first() → юзер с telegram_id/lang."""
    user = MagicMock()
    user.id = 1
    user.telegram_id = telegram_id
    user.language = language
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db, user


def _db_without_user():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


class TestBuildNotificationText:
    def test_approved_text_ru(self) -> None:
        from access_control.services.resident_notify import ResidentNotification

        n = ResidentNotification(
            kind=KIND_VEHICLE_REQUEST_RESOLVED,
            recipient_user_id=1,
            status="approved",
        )
        text = build_notification_text(n, "ru")
        assert text is not None
        assert "одобрен" in text.lower()

    def test_rejected_text_with_comment(self) -> None:
        from access_control.services.resident_notify import ResidentNotification

        n = ResidentNotification(
            kind=KIND_VEHICLE_REQUEST_RESOLVED,
            recipient_user_id=1,
            status="rejected",
            comment="Нет места на парковке",
        )
        text = build_notification_text(n, "ru")
        assert text is not None
        assert "отклонен" in text.lower()
        assert "Нет места на парковке" in text

    def test_unknown_kind_returns_none(self) -> None:
        from access_control.services.resident_notify import ResidentNotification

        n = ResidentNotification(kind="some_other_kind", recipient_user_id=1, status="approved")
        assert build_notification_text(n, "ru") is None

    def test_unknown_status_returns_none(self) -> None:
        from access_control.services.resident_notify import ResidentNotification

        n = ResidentNotification(
            kind=KIND_VEHICLE_REQUEST_RESOLVED, recipient_user_id=1, status="weird"
        )
        assert build_notification_text(n, "ru") is None


class TestHandlePayload:
    async def test_approved_sends_to_telegram_id(self) -> None:
        db, _ = _db_with_user(telegram_id=777)
        bot = AsyncMock()
        payload = {
            "kind": KIND_VEHICLE_REQUEST_RESOLVED,
            "recipient_user_id": 1,
            "request_id": 42,
            "status": "approved",
        }
        await handle_payload(bot, db, payload)
        bot.send_message.assert_awaited_once()
        args = bot.send_message.call_args.args
        assert args[0] == 777
        assert "одобрен" in args[1].lower()

    async def test_rejected_includes_comment(self) -> None:
        db, _ = _db_with_user()
        bot = AsyncMock()
        payload = {
            "kind": KIND_VEHICLE_REQUEST_RESOLVED,
            "recipient_user_id": 1,
            "status": "rejected",
            "comment": "Дубликат заявки",
        }
        await handle_payload(bot, db, payload)
        bot.send_message.assert_awaited_once()
        text = bot.send_message.call_args.args[1]
        assert "отклонен" in text.lower()
        assert "Дубликат заявки" in text

    async def test_unknown_recipient_does_not_send(self) -> None:
        db = _db_without_user()
        bot = AsyncMock()
        payload = {
            "kind": KIND_VEHICLE_REQUEST_RESOLVED,
            "recipient_user_id": 999,
            "status": "approved",
        }
        # Не падает
        await handle_payload(bot, db, payload)
        bot.send_message.assert_not_awaited()

    async def test_missing_recipient_does_not_send(self) -> None:
        db, _ = _db_with_user()
        bot = AsyncMock()
        payload = {"kind": KIND_VEHICLE_REQUEST_RESOLVED, "status": "approved"}
        await handle_payload(bot, db, payload)
        bot.send_message.assert_not_awaited()

    async def test_delivery_failure_is_swallowed(self) -> None:
        """Юзер заблокировал бота → исключение доставки не пробрасывается."""
        db, _ = _db_with_user()
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Forbidden: bot was blocked by the user")
        payload = {
            "kind": KIND_VEHICLE_REQUEST_RESOLVED,
            "recipient_user_id": 1,
            "status": "approved",
        }
        # Не падает
        await handle_payload(bot, db, payload)
        bot.send_message.assert_awaited_once()

    async def test_unknown_kind_does_not_send(self) -> None:
        db, _ = _db_with_user()
        bot = AsyncMock()
        payload = {"kind": "other", "recipient_user_id": 1, "status": "approved"}
        await handle_payload(bot, db, payload)
        bot.send_message.assert_not_awaited()


class TestDisputedEntry:
    """Спорный въезд: текст + инлайн-клавиатура «Подтвердить/Отклонить» (§9.4)."""

    def _notification(self):
        from access_control.services.resident_notify import ResidentNotification

        return ResidentNotification(
            kind=KIND_DISPUTED_ENTRY,
            recipient_user_id=1,
            decision_id=77,
            camera_event_id=5,
            plate_masked="•••123",
            zone=3,
            status="manual_review",
        )

    def test_text_mentions_plate(self) -> None:
        text = build_notification_text(self._notification(), "ru")
        assert text is not None
        assert "•••123" in text

    def test_text_uz(self) -> None:
        text = build_notification_text(self._notification(), "uz")
        assert text is not None
        assert "•••123" in text

    def test_reply_markup_has_two_buttons(self) -> None:
        markup = build_reply_markup(self._notification(), "ru")
        assert markup is not None
        rows = markup.inline_keyboard
        buttons = [b for row in rows for b in row]
        assert len(buttons) == 2
        cbs = {b.callback_data for b in buttons}
        assert cbs == {"acc_dispute:77:confirm", "acc_dispute:77:deny"}

    def test_callback_data_within_64_bytes(self) -> None:
        markup = build_reply_markup(self._notification(), "ru")
        for row in markup.inline_keyboard:
            for b in row:
                assert len(b.callback_data.encode("utf-8")) <= 64

    def test_other_kind_has_no_markup(self) -> None:
        from access_control.services.resident_notify import ResidentNotification

        n = ResidentNotification(
            kind=KIND_VEHICLE_REQUEST_RESOLVED, recipient_user_id=1, status="approved"
        )
        assert build_reply_markup(n, "ru") is None

    async def test_handle_payload_sends_with_markup(self) -> None:
        db, _ = _db_with_user(telegram_id=888)
        bot = AsyncMock()
        payload = {
            "kind": KIND_DISPUTED_ENTRY,
            "recipient_user_id": 1,
            "decision_id": 77,
            "camera_event_id": 5,
            "plate_masked": "•••123",
            "zone": 3,
            "status": "manual_review",
        }
        await handle_payload(bot, db, payload)
        bot.send_message.assert_awaited_once()
        assert bot.send_message.call_args.args[0] == 888
        markup = bot.send_message.call_args.kwargs.get("reply_markup")
        assert markup is not None
        buttons = [b for row in markup.inline_keyboard for b in row]
        assert len(buttons) == 2

    async def test_vehicle_resolved_sends_without_markup(self) -> None:
        """Прочие kinds доставляются БЕЗ клавиатуры (как раньше)."""
        db, _ = _db_with_user()
        bot = AsyncMock()
        payload = {
            "kind": KIND_VEHICLE_REQUEST_RESOLVED,
            "recipient_user_id": 1,
            "status": "approved",
        }
        await handle_payload(bot, db, payload)
        bot.send_message.assert_awaited_once()
        assert bot.send_message.call_args.kwargs.get("reply_markup") is None


class TestParsePayload:
    def test_valid_json(self) -> None:
        assert parse_payload('{"kind": "x"}') == {"kind": "x"}

    def test_invalid_json_returns_none(self) -> None:
        # Не бросает
        assert parse_payload("{not valid json") is None

    def test_non_object_json_returns_none(self) -> None:
        assert parse_payload("[1, 2, 3]") is None
        assert parse_payload("42") is None
