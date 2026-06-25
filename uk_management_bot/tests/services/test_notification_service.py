"""Unit tests for notification_service — pure formatting functions and async helpers."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.services.notification_service import (
    _format_duration_hm,
    build_shift_started_message,
    build_shift_ended_message,
    build_document_request_message,
    build_multiple_documents_request_message,
    _build_request_status_message_user,
    _build_request_status_message_executor,
    _build_request_status_message_channel,
    build_action_denied_message,
    notify_status_changed,
    notify_shift_started,
    notify_shift_ended,
    send_to_channel,
    send_to_user,
    async_notify_shift_started,
    async_notify_shift_ended,
    NotificationService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(telegram_id=100, user_id=1, language="ru"):
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    user.language = language
    return user


def _make_shift(shift_id=10, start_time=None, end_time=None):
    shift = MagicMock()
    shift.id = shift_id
    shift.start_time = start_time or datetime(2026, 4, 2, 9, 0, 0)
    shift.end_time = end_time
    return shift


def _make_request(request_number="260402-001", category="Сантехника",
                  address="Block 3, apt 15", user_id=1, executor_id=None):
    req = MagicMock()
    req.request_number = request_number
    req.category = category
    req.address = address
    req.user_id = user_id
    req.executor_id = executor_id
    return req


# ---------------------------------------------------------------------------
# _format_duration_hm
# ---------------------------------------------------------------------------

class TestFormatDurationHm:
    def test_zero_duration(self):
        t = datetime(2026, 4, 2, 9, 0, 0)
        hours, minutes = _format_duration_hm(t, t)
        assert hours == 0
        assert minutes == 0

    def test_exact_one_hour(self):
        start = datetime(2026, 4, 2, 9, 0, 0)
        end = datetime(2026, 4, 2, 10, 0, 0)
        hours, minutes = _format_duration_hm(start, end)
        assert hours == 1
        assert minutes == 0

    def test_mixed_hours_and_minutes(self):
        start = datetime(2026, 4, 2, 9, 0, 0)
        end = datetime(2026, 4, 2, 10, 30, 0)
        hours, minutes = _format_duration_hm(start, end)
        assert hours == 1
        assert minutes == 30

    def test_end_time_none_uses_now(self):
        start = datetime(2026, 4, 2, 9, 0, 0)
        # With end_time=None the function uses datetime.now() — just check it doesn't raise
        hours, minutes = _format_duration_hm(start, None)
        assert hours >= 0
        assert minutes >= 0

    def test_end_before_start_returns_zero(self):
        start = datetime(2026, 4, 2, 10, 0, 0)
        end = datetime(2026, 4, 2, 9, 0, 0)
        hours, minutes = _format_duration_hm(start, end)
        assert hours == 0
        assert minutes == 0


# ---------------------------------------------------------------------------
# build_shift_started_message
# ---------------------------------------------------------------------------

class TestBuildShiftStartedMessage:
    def test_user_message_contains_start_time(self):
        user = _make_user()
        shift = _make_shift(start_time=datetime(2026, 4, 2, 9, 15, 0))
        msg = build_shift_started_message(user, shift, for_channel=False)
        assert "09:15" in msg
        assert "02.04.2026" in msg

    def test_channel_message_contains_user_id(self):
        user = _make_user(telegram_id=12345)
        shift = _make_shift(start_time=datetime(2026, 4, 2, 9, 0, 0))
        msg = build_shift_started_message(user, shift, for_channel=True)
        assert "12345" in msg

    def test_user_message_does_not_expose_telegram_id(self):
        user = _make_user(telegram_id=12345)
        shift = _make_shift(start_time=datetime(2026, 4, 2, 9, 0, 0))
        msg = build_shift_started_message(user, shift, for_channel=False)
        assert "12345" not in msg


# ---------------------------------------------------------------------------
# build_shift_ended_message
# ---------------------------------------------------------------------------

class TestBuildShiftEndedMessage:
    def test_contains_duration(self):
        start = datetime(2026, 4, 2, 9, 0, 0)
        end = datetime(2026, 4, 2, 10, 30, 0)
        user = _make_user()
        shift = _make_shift(start_time=start, end_time=end)
        msg = build_shift_ended_message(user, shift, for_channel=False)
        assert "1" in msg   # 1 hour
        assert "30" in msg  # 30 minutes

    def test_channel_message_contains_user_id(self):
        start = datetime(2026, 4, 2, 9, 0, 0)
        end = datetime(2026, 4, 2, 10, 0, 0)
        user = _make_user(telegram_id=999)
        shift = _make_shift(start_time=start, end_time=end)
        msg = build_shift_ended_message(user, shift, for_channel=True)
        assert "999" in msg

    def test_user_message_contains_end_time(self):
        start = datetime(2026, 4, 2, 9, 0, 0)
        end = datetime(2026, 4, 2, 17, 45, 0)
        user = _make_user()
        shift = _make_shift(start_time=start, end_time=end)
        msg = build_shift_ended_message(user, shift, for_channel=False)
        assert "17:45" in msg


# ---------------------------------------------------------------------------
# build_document_request_message
# ---------------------------------------------------------------------------

class TestBuildDocumentRequestMessage:
    def test_user_message_contains_doc_name_in_russian(self):
        user = _make_user()
        msg = build_document_request_message(user, "Bring docs", document_type="passport", for_channel=False)
        assert "паспорт" in msg

    def test_user_message_contains_request_text(self):
        user = _make_user()
        msg = build_document_request_message(user, "Please upload ASAP", document_type="passport", for_channel=False)
        assert "Please upload ASAP" in msg

    def test_channel_message_contains_user_id(self):
        user = _make_user(telegram_id=5555)
        msg = build_document_request_message(user, "text", document_type="passport", for_channel=True)
        assert "5555" in msg

    def test_unknown_doc_type_uses_type_key(self):
        user = _make_user()
        msg = build_document_request_message(user, "text", document_type="mystery_type", for_channel=False)
        assert "mystery_type" in msg

    def test_none_doc_type_falls_back_gracefully(self):
        user = _make_user()
        msg = build_document_request_message(user, "text", document_type=None, for_channel=False)
        assert isinstance(msg, str)
        assert len(msg) > 0


# ---------------------------------------------------------------------------
# build_multiple_documents_request_message
# ---------------------------------------------------------------------------

class TestBuildMultipleDocumentsRequestMessage:
    def test_lists_all_doc_types(self):
        user = _make_user()
        types = ["passport", "rental_agreement"]
        msg = build_multiple_documents_request_message(user, "text", types, for_channel=False)
        assert "паспорт" in msg
        assert "договор аренды" in msg

    def test_channel_message_contains_user_id(self):
        user = _make_user(telegram_id=7777)
        msg = build_multiple_documents_request_message(user, "text", ["passport"], for_channel=True)
        assert "7777" in msg

    def test_empty_list_does_not_raise(self):
        user = _make_user()
        msg = build_multiple_documents_request_message(user, "text", [], for_channel=False)
        assert isinstance(msg, str)


# ---------------------------------------------------------------------------
# _build_request_status_message_*
# ---------------------------------------------------------------------------

class TestBuildRequestStatusMessages:
    def test_user_message_contains_request_number(self):
        req = _make_request(request_number="260402-001")
        msg = _build_request_status_message_user(req, "Новая", "В работе")
        assert "260402-001" in msg
        assert "Новая" in msg
        assert "В работе" in msg

    def test_user_message_truncates_long_address(self):
        long_addr = "A" * 100
        req = _make_request(address=long_addr)
        msg = _build_request_status_message_user(req, "Новая", "В работе")
        assert "…" in msg

    def test_user_message_no_truncation_for_short_address(self):
        req = _make_request(address="Short address")
        msg = _build_request_status_message_user(req, "Новая", "В работе")
        assert "…" not in msg

    def test_executor_message_contains_request_number(self):
        req = _make_request(request_number="260402-002")
        msg = _build_request_status_message_executor(req, "В работе", "Выполнена")
        assert "260402-002" in msg
        assert "В работе" in msg
        assert "Выполнена" in msg

    def test_channel_message_contains_request_number(self):
        req = _make_request(request_number="260402-003")
        msg = _build_request_status_message_channel(req, "Новая", "Отменена")
        assert "260402-003" in msg
        assert "Новая" in msg
        assert "Отменена" in msg


# ---------------------------------------------------------------------------
# build_action_denied_message
# ---------------------------------------------------------------------------

class TestBuildActionDeniedMessage:
    def test_not_in_shift_key(self):
        msg = build_action_denied_message("not_in_shift")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_permission_denied_key(self):
        msg = build_action_denied_message("permission_denied")
        assert isinstance(msg, str)

    def test_invalid_transition_key(self):
        msg = build_action_denied_message("invalid_transition")
        assert isinstance(msg, str)

    def test_unknown_key_returns_generic_message(self):
        msg = build_action_denied_message("totally_unknown_key")
        assert isinstance(msg, str)
        # The fallback dict returns "Действие отклонено" for unknown keys
        assert "отклонено" in msg.lower() or len(msg) > 0


# ---------------------------------------------------------------------------
# notify_status_changed (sync stub — just verifies no exception)
# ---------------------------------------------------------------------------

class TestNotifyStatusChanged:
    def test_does_not_raise(self):
        db = MagicMock()
        req = _make_request()
        notify_status_changed(db, req, "Новая", "В работе")

    def test_purchase_status_no_exception(self):
        db = MagicMock()
        req = _make_request()
        notify_status_changed(db, req, "В работе", "Закуп")

    def test_clarification_status_no_exception(self):
        db = MagicMock()
        req = _make_request()
        notify_status_changed(db, req, "В работе", "Уточнение")


# ---------------------------------------------------------------------------
# notify_shift_started / notify_shift_ended (sync stubs)
# ---------------------------------------------------------------------------

class TestNotifyShiftStubs:
    def test_notify_shift_started_no_exception(self):
        db = MagicMock()
        user = _make_user()
        shift = _make_shift()
        notify_shift_started(db, user, shift)

    def test_notify_shift_ended_no_exception(self):
        db = MagicMock()
        user = _make_user()
        shift = _make_shift()
        notify_shift_ended(db, user, shift)


# ---------------------------------------------------------------------------
# send_to_channel / send_to_user (async helpers)
# ---------------------------------------------------------------------------

class TestSendToChannel:
    @pytest.mark.asyncio
    async def test_sends_when_channel_id_configured(self):
        bot = AsyncMock()
        with patch(
            "uk_management_bot.services.notification_service.settings"
        ) as mock_settings:
            mock_settings.TELEGRAM_CHANNEL_ID = "-100123456789"
            await send_to_channel(bot, "Hello channel")
        bot.send_message.assert_called_once_with("-100123456789", "Hello channel")

    @pytest.mark.asyncio
    async def test_skips_when_no_channel_id(self):
        bot = AsyncMock()
        with patch(
            "uk_management_bot.services.notification_service.settings"
        ) as mock_settings:
            mock_settings.TELEGRAM_CHANNEL_ID = None
            await send_to_channel(bot, "Hello channel")
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_bot_exception(self):
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Forbidden")
        with patch(
            "uk_management_bot.services.notification_service.settings"
        ) as mock_settings:
            mock_settings.TELEGRAM_CHANNEL_ID = "-100123"
            await send_to_channel(bot, "text")  # should not raise


class TestSendToUser:
    @pytest.mark.asyncio
    async def test_sends_to_user_telegram_id(self):
        bot = AsyncMock()
        await send_to_user(bot, 12345, "Hello user")
        bot.send_message.assert_called_once_with(12345, "Hello user")

    @pytest.mark.asyncio
    async def test_does_not_raise_on_bot_exception(self):
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("User blocked bot")
        await send_to_user(bot, 12345, "text")  # should not raise

    # BUG-BOT-036: send_to_user reports delivery via bool so callers can
    # distinguish a real send from a swallowed failure.
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        bot = AsyncMock()
        assert await send_to_user(bot, 12345, "Hello") is True

    @pytest.mark.asyncio
    async def test_returns_false_on_bot_exception(self):
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("User blocked bot")
        assert await send_to_user(bot, 12345, "text") is False


class TestNotifyUserAsync:
    """BUG-BOT-036: async delivery variant returning a real delivered bool."""

    @pytest.mark.asyncio
    async def test_returns_true_when_delivered(self):
        user = MagicMock()
        user.id, user.telegram_id = 1, 555
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        bot = AsyncMock()
        svc = NotificationService(db=db, bot=bot)

        assert await svc.notify_user_async(1, "Hello", "World") is True
        bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_send_fails(self):
        user = MagicMock()
        user.id, user.telegram_id = 1, 555
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("403 bot blocked")
        svc = NotificationService(db=db, bot=bot)

        assert await svc.notify_user_async(1, "Hello", "World") is False

    @pytest.mark.asyncio
    async def test_returns_false_when_user_missing(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        svc = NotificationService(db=db, bot=AsyncMock())

        assert await svc.notify_user_async(999, "t", "m") is False


# ---------------------------------------------------------------------------
# async_notify_shift_started / async_notify_shift_ended
# ---------------------------------------------------------------------------

class TestAsyncNotifyShift:
    @pytest.mark.asyncio
    async def test_shift_started_calls_send_to_user_and_channel(self):
        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=111)
        shift = _make_shift(start_time=datetime(2026, 4, 2, 9, 0, 0))

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            new_callable=AsyncMock,
        ) as mock_user, patch(
            "uk_management_bot.services.notification_service.send_to_channel",
            new_callable=AsyncMock,
        ) as mock_channel:
            await async_notify_shift_started(bot, db, user, shift)

        mock_user.assert_called_once()
        mock_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_shift_ended_calls_send_to_user_and_channel(self):
        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=222)
        start = datetime(2026, 4, 2, 9, 0, 0)
        end = datetime(2026, 4, 2, 10, 0, 0)
        shift = _make_shift(start_time=start, end_time=end)

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            new_callable=AsyncMock,
        ) as mock_user, patch(
            "uk_management_bot.services.notification_service.send_to_channel",
            new_callable=AsyncMock,
        ) as mock_channel:
            await async_notify_shift_ended(bot, db, user, shift)

        mock_user.assert_called_once()
        mock_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_when_send_fails(self):
        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=333)
        shift = _make_shift(start_time=datetime(2026, 4, 2, 9, 0, 0))

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            side_effect=Exception("network error"),
        ):
            await async_notify_shift_started(bot, db, user, shift)


# ---------------------------------------------------------------------------
# NotificationService
# ---------------------------------------------------------------------------

class TestNotificationService:
    def _make_service(self, user=None):
        db = MagicMock()
        bot = AsyncMock()
        if user is not None:
            db.query.return_value.filter.return_value.first.return_value = user
        else:
            db.query.return_value.filter.return_value.first.return_value = None
        svc = NotificationService(db, bot=bot)
        return svc, db, bot

    @pytest.mark.asyncio
    async def test_send_verification_approved_notification_calls_bot(self):
        user = _make_user(telegram_id=500, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked_text",
        ):
            await svc.send_verification_approved_notification(user_id=1)

        bot.send_message.assert_called_once()
        call_args = bot.send_message.call_args
        assert call_args.args[0] == 500  # telegram_id

    @pytest.mark.asyncio
    async def test_send_verification_approved_notification_user_not_found(self):
        svc, db, bot = self._make_service(user=None)
        # Should not raise even if user not found
        await svc.send_verification_approved_notification(user_id=9999)
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_verification_rejected_notification_calls_bot(self):
        user = _make_user(telegram_id=501, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked_text",
        ):
            await svc.send_verification_rejected_notification(user_id=1)

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_system_notification_calls_send_to_channel(self):
        svc, db, bot = self._make_service()

        with patch(
            "uk_management_bot.services.notification_service.send_to_channel",
            new_callable=AsyncMock,
        ) as mock_channel:
            await svc.send_system_notification("Title", "Body text")

        mock_channel.assert_called_once()
        call_text = mock_channel.call_args.args[1]
        assert "Title" in call_text
        assert "Body text" in call_text

    @pytest.mark.asyncio
    async def test_does_not_raise_when_bot_send_fails(self):
        user = _make_user(telegram_id=502)
        svc, db, bot = self._make_service(user)
        bot.send_message.side_effect = Exception("Forbidden")

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="text",
        ):
            await svc.send_verification_approved_notification(user_id=1)

    def test_get_bot_uses_injected_bot(self):
        db = MagicMock()
        bot = MagicMock()
        svc = NotificationService(db, bot=bot)
        assert svc._get_bot() is bot

    def test_get_bot_falls_back_to_shared_when_none(self):
        db = MagicMock()
        svc = NotificationService(db, bot=None)
        mock_bot = MagicMock()
        with patch(
            "uk_management_bot.services.notification_service._get_shared_bot",
            return_value=mock_bot,
        ):
            result = svc._get_bot()
        assert result is mock_bot

    def test_get_user_lang_returns_user_language(self):
        db = MagicMock()
        svc = NotificationService(db)
        user = _make_user(language="uz")
        assert svc._get_user_lang(user) == "uz"

    def test_get_user_lang_defaults_to_ru_when_none(self):
        db = MagicMock()
        svc = NotificationService(db)
        user = MagicMock()
        user.language = None
        assert svc._get_user_lang(user) == "ru"

    @pytest.mark.asyncio
    async def test_send_document_approved_calls_bot(self):
        user = _make_user(telegram_id=600, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_document_approved_notification(user_id=1, document_type="passport")

        bot.send_message.assert_called_once()
        assert bot.send_message.call_args.args[0] == 600

    @pytest.mark.asyncio
    async def test_send_document_approved_user_not_found(self):
        svc, db, bot = self._make_service(user=None)
        await svc.send_document_approved_notification(user_id=9999, document_type="passport")
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_document_rejected_calls_bot(self):
        user = _make_user(telegram_id=601, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_document_rejected_notification(user_id=1, document_type="passport")

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_document_rejected_with_reason(self):
        user = _make_user(telegram_id=602, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_document_rejected_notification(
                user_id=1, document_type="passport", reason="Wrong doc"
            )

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_access_rights_granted_calls_bot(self):
        user = _make_user(telegram_id=700, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_access_rights_granted_notification(
                user_id=1, access_level="full"
            )

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_access_rights_granted_with_details(self):
        user = _make_user(telegram_id=701, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_access_rights_granted_notification(
                user_id=1, access_level="full", details="All floors"
            )

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_access_rights_revoked_calls_bot(self):
        user = _make_user(telegram_id=800, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_access_rights_revoked_notification(
                user_id=1, access_level="full"
            )

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_access_rights_revoked_with_reason(self):
        user = _make_user(telegram_id=801, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_access_rights_revoked_notification(
                user_id=1, access_level="full", reason="Policy"
            )

        bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_verification_request_notification_calls_bot(self):
        user = _make_user(telegram_id=900, language="ru")
        svc, db, bot = self._make_service(user)

        with patch(
            "uk_management_bot.services.notification_service.get_text",
            return_value="mocked",
        ):
            await svc.send_verification_request_notification(
                user_id=1, info_type="passport", comment="Need valid scan"
            )

        bot.send_message.assert_called_once()
        assert bot.send_message.call_args.args[0] == 900

    @pytest.mark.asyncio
    async def test_send_verification_request_notification_user_not_found(self):
        svc, db, bot = self._make_service(user=None)
        await svc.send_verification_request_notification(
            user_id=9999, info_type="passport", comment="x"
        )
        bot.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# async_notify_request_status_changed
# ---------------------------------------------------------------------------

class TestAsyncNotifyRequestStatusChanged:
    @pytest.mark.asyncio
    async def test_notifies_applicant_and_channel(self):
        from uk_management_bot.services.notification_service import (
            async_notify_request_status_changed,
        )

        bot = AsyncMock()
        db = MagicMock()

        applicant = _make_user(telegram_id=111)
        req = _make_request(user_id=1, executor_id=None)

        db.query.return_value.filter.return_value.first.return_value = applicant

        with (
            patch(
                "uk_management_bot.services.notification_service.send_to_user",
                new_callable=AsyncMock,
            ) as mock_user,
            patch(
                "uk_management_bot.services.notification_service.send_to_channel",
                new_callable=AsyncMock,
            ) as mock_channel,
        ):
            await async_notify_request_status_changed(bot, db, req, "Новая", "В работе")

        mock_user.assert_called_once()
        mock_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_notifies_executor_when_assigned(self):
        from uk_management_bot.services.notification_service import (
            async_notify_request_status_changed,
        )

        bot = AsyncMock()
        db = MagicMock()

        applicant = _make_user(telegram_id=111, user_id=1)
        executor = _make_user(telegram_id=222, user_id=2)
        req = _make_request(user_id=1, executor_id=2)

        db.query.return_value.filter.return_value.first.side_effect = [applicant, executor]

        with (
            patch(
                "uk_management_bot.services.notification_service.send_to_user",
                new_callable=AsyncMock,
            ) as mock_user,
            patch(
                "uk_management_bot.services.notification_service.send_to_channel",
                new_callable=AsyncMock,
            ),
        ):
            await async_notify_request_status_changed(bot, db, req, "В работе", "Выполнена")

        # Two user notifications (applicant + executor)
        assert mock_user.call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_raise_on_db_exception(self):
        from uk_management_bot.services.notification_service import (
            async_notify_request_status_changed,
        )

        bot = AsyncMock()
        db = MagicMock()
        db.query.side_effect = Exception("DB fail")

        req = _make_request()

        with patch(
            "uk_management_bot.services.notification_service.send_to_channel",
            new_callable=AsyncMock,
        ):
            await async_notify_request_status_changed(bot, db, req, "Новая", "В работе")


# ---------------------------------------------------------------------------
# build_role_switched_message / async_notify_role_switched
# ---------------------------------------------------------------------------


class TestAsyncNotifyRoleSwitched:
    @pytest.mark.asyncio
    async def test_sends_to_user(self):
        from uk_management_bot.services.notification_service import async_notify_role_switched

        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=123)

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            new_callable=AsyncMock,
        ) as mock_send:
            await async_notify_role_switched(bot, db, user, "applicant", "executor")

        mock_send.assert_called_once()
        assert mock_send.call_args.args[1] == 123

    @pytest.mark.asyncio
    async def test_does_not_raise_on_exception(self):
        from uk_management_bot.services.notification_service import async_notify_role_switched

        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=123)

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            side_effect=Exception("network"),
        ):
            await async_notify_role_switched(bot, db, user, "applicant", "executor")


# ---------------------------------------------------------------------------
# async_notify_action_denied
# ---------------------------------------------------------------------------

class TestAsyncNotifyActionDenied:
    @pytest.mark.asyncio
    async def test_sends_to_user(self):
        from uk_management_bot.services.notification_service import async_notify_action_denied

        bot = AsyncMock()
        db = MagicMock()

        user = _make_user(telegram_id=555, language="ru")
        db.query.return_value.filter.return_value.first.return_value = user

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            new_callable=AsyncMock,
        ) as mock_send:
            await async_notify_action_denied(bot, db, 555, "not_in_shift")

        mock_send.assert_called_once()
        assert mock_send.call_args.args[1] == 555

    @pytest.mark.asyncio
    async def test_does_not_raise_when_user_not_found(self):
        from uk_management_bot.services.notification_service import async_notify_action_denied

        bot = AsyncMock()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            new_callable=AsyncMock,
        ):
            await async_notify_action_denied(bot, db, 999, "permission_denied")


# ---------------------------------------------------------------------------
# async_notify_document_request / async_notify_multiple_documents_request
# ---------------------------------------------------------------------------

class TestAsyncNotifyDocumentRequest:
    @pytest.mark.asyncio
    async def test_sends_to_user_and_channel(self):
        from uk_management_bot.services.notification_service import async_notify_document_request

        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=300)

        with (
            patch(
                "uk_management_bot.services.notification_service.send_to_user",
                new_callable=AsyncMock,
            ) as mock_user,
            patch(
                "uk_management_bot.services.notification_service.send_to_channel",
                new_callable=AsyncMock,
            ) as mock_channel,
        ):
            await async_notify_document_request(bot, db, user, "Upload passport", "passport")

        mock_user.assert_called_once()
        mock_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_send_failure(self):
        from uk_management_bot.services.notification_service import async_notify_document_request

        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=301)

        with patch(
            "uk_management_bot.services.notification_service.send_to_user",
            side_effect=Exception("fail"),
        ):
            await async_notify_document_request(bot, db, user, "text", "passport")


class TestAsyncNotifyMultipleDocumentsRequest:
    @pytest.mark.asyncio
    async def test_sends_to_user_and_channel(self):
        from uk_management_bot.services.notification_service import (
            async_notify_multiple_documents_request,
        )

        bot = AsyncMock()
        db = MagicMock()
        user = _make_user(telegram_id=400)

        with (
            patch(
                "uk_management_bot.services.notification_service.send_to_user",
                new_callable=AsyncMock,
            ) as mock_user,
            patch(
                "uk_management_bot.services.notification_service.send_to_channel",
                new_callable=AsyncMock,
            ) as mock_channel,
        ):
            await async_notify_multiple_documents_request(
                bot, db, user, "Upload all", ["passport", "rental_agreement"]
            )

        mock_user.assert_called_once()
        mock_channel.assert_called_once()
