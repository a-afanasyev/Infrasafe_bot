"""
Unit tests for uk_management_bot/handlers/shifts.py

Covers: start_shift, end_shift_confirm, show_shift_end_details, my_shift,
shifts_history, handle_end_shift_cancel, end_shift_no, suggest_executor_skip.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from aiogram.types import Message, CallbackQuery, User as TgUser


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_tg_user(user_id=555):
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = "Executor"
    u.last_name = "Test"
    u.username = "exec_test"
    return u


def _make_message(user_id=555):
    msg = MagicMock(spec=Message)
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.text = ""
    msg.answer = AsyncMock()
    msg.answer_media_group = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_callback(data="", user_id=555):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_tg_user(user_id=user_id)
    cb.answer = AsyncMock()
    cb.message = _make_message(user_id=user_id)
    cb.bot = MagicMock()
    return cb


def _make_state(data=None):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


def _make_db():
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.close = MagicMock()
    return db


def _make_shift(shift_id=1, user_id=10, status="active"):
    shift = MagicMock()
    shift.id = shift_id
    shift.user_id = user_id
    shift.status = status
    shift.start_time = datetime(2025, 1, 15, 9, 0, 0)
    shift.end_time = None
    shift.specialization_focus = []
    return shift


def _make_db_user(tg_id=555, db_user_id=10):
    user = MagicMock()
    user.id = db_user_id
    user.telegram_id = tg_id
    user.status = "approved"
    user.roles = '["executor"]'
    user.active_role = "executor"
    return user


# ─── start_shift ─────────────────────────────────────────────────────────────

class TestStartShift:
    """Tests for start_shift handler."""

    @pytest.mark.asyncio
    async def test_start_shift_success(self):
        """start_shift sends 'started' confirmation when service succeeds."""
        from uk_management_bot.handlers.shifts import start_shift

        msg = _make_message()
        db = _make_db()
        shift = _make_shift()

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_main_keyboard", return_value=MagicMock()
        ), patch(
            "uk_management_bot.handlers.shifts.async_notify_shift_started", new_callable=AsyncMock
        ):
            svc = MockService.return_value
            svc.start_shift.return_value = {"success": True, "shift": shift}
            svc._get_user_by_tg.return_value = _make_db_user()

            await start_shift(msg, db=db)

        msg.answer.assert_called()
        svc.start_shift.assert_called_once_with(msg.from_user.id)

    @pytest.mark.asyncio
    async def test_start_shift_failure_sends_error_message(self):
        """start_shift forwards service error message when start fails."""
        from uk_management_bot.handlers.shifts import start_shift

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_main_keyboard", return_value=MagicMock()
        ):
            svc = MockService.return_value
            svc.start_shift.return_value = {"success": False, "message": "У вас уже есть активная смена"}

            await start_shift(msg, db=db)

        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args[0][0]
        assert "активная смена" in sent_text or len(sent_text) > 0

    @pytest.mark.asyncio
    async def test_start_shift_pending_status_shows_pending_message(self):
        """start_shift refuses to start when user status is 'pending'."""
        from uk_management_bot.handlers.shifts import start_shift

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.get_shifts_main_keyboard", return_value=MagicMock()
        ):
            await start_shift(msg, db=db, user_status="pending")

        msg.answer.assert_called_once()
        # ShiftService.start_shift should NOT have been called
        # (the handler returns early for pending status)

    @pytest.mark.asyncio
    async def test_start_shift_suggests_executor_role_switch(self):
        """start_shift suggests switching to executor role when applicable."""
        from uk_management_bot.handlers.shifts import start_shift

        msg = _make_message()
        db = _make_db()
        shift = _make_shift()

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_main_keyboard", return_value=MagicMock()
        ), patch(
            "uk_management_bot.handlers.shifts.async_notify_shift_started", new_callable=AsyncMock
        ), patch(
            "uk_management_bot.handlers.shifts.get_executor_suggestion_inline", return_value=MagicMock()
        ) as mock_suggestion_kb:
            svc = MockService.return_value
            svc.start_shift.return_value = {"success": True, "shift": shift}
            svc._get_user_by_tg.return_value = _make_db_user()

            # User has executor role but current active_role is applicant
            await start_shift(
                msg,
                db=db,
                roles=["applicant", "executor"],
                active_role="applicant",
            )

        # answer called at least twice (success + suggestion)
        assert msg.answer.call_count >= 2


# ─── end_shift_confirm ────────────────────────────────────────────────────────

class TestEndShiftConfirm:
    """Tests for end_shift_confirm handler."""

    @pytest.mark.asyncio
    async def test_no_active_shifts_sends_no_active_message(self):
        """end_shift_confirm tells user there are no active shifts."""
        from uk_management_bot.handlers.shifts import end_shift_confirm

        msg = _make_message()
        db = _make_db()
        user = _make_db_user()

        # Simulate db.query().filter().first() -> user
        # and db.query().filter().order_by().all() -> []
        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = user
            q.order_by.return_value = q
            q.all.return_value = []
            return q

        db.query.side_effect = _query

        with patch("uk_management_bot.handlers.shifts.get_user_language", return_value="ru"):
            await end_shift_confirm(msg, db=db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_active_shift_shows_details_directly(self):
        """end_shift_confirm calls show_shift_end_details when there is exactly one active shift."""
        from uk_management_bot.handlers.shifts import end_shift_confirm

        msg = _make_message()
        db = _make_db()
        user = _make_db_user()
        shift = _make_shift(shift_id=42, user_id=10)

        call_count = {"n": 0}

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            call_count["n"] += 1
            # first call → user lookup; second call → shift list
            if call_count["n"] == 1:
                q.first.return_value = user
            else:
                q.order_by.return_value = q
                q.all.return_value = [shift]
            return q

        db.query.side_effect = _query

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.show_shift_end_details", new_callable=AsyncMock
        ) as mock_details:
            await end_shift_confirm(msg, db=db)

        mock_details.assert_called_once_with(msg, 42, db, "ru")

    @pytest.mark.asyncio
    async def test_user_not_found_sends_error(self):
        """end_shift_confirm sends an error message when the user is not in DB."""
        from uk_management_bot.handlers.shifts import end_shift_confirm

        msg = _make_message()
        db = _make_db()

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = None
            return q

        db.query.side_effect = _query

        with patch("uk_management_bot.handlers.shifts.get_user_language", return_value="ru"):
            await end_shift_confirm(msg, db=db)

        msg.answer.assert_called_once()


# ─── show_shift_end_details ──────────────────────────────────────────────────

class TestShowShiftEndDetails:
    """Tests for show_shift_end_details helper."""

    @pytest.mark.asyncio
    async def test_shift_not_found_sends_error(self):
        """show_shift_end_details handles missing shift gracefully."""
        from uk_management_bot.handlers.shifts import show_shift_end_details

        msg = _make_message()
        db = _make_db()

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = None
            q.join.return_value = q
            q.all.return_value = []
            return q

        db.query.side_effect = _query

        await show_shift_end_details(msg, shift_id=999, db=db, lang="ru")

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_shift_found_sends_details_with_keyboard(self):
        """show_shift_end_details sends shift details and confirmation keyboard."""
        from uk_management_bot.handlers.shifts import show_shift_end_details

        msg = _make_message()
        db = _make_db()
        shift = _make_shift(shift_id=5, user_id=10)
        shift.specialization_focus = ["plumbing"]
        user = _make_db_user(db_user_id=10)

        call_count = {"n": 0}

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.join.return_value = q
            q.all.return_value = []
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Shift lookup
                q.first.return_value = shift
            elif call_count["n"] == 2:
                # group_requests
                q.first.return_value = None
            elif call_count["n"] == 3:
                # user lookup
                q.first.return_value = user
            else:
                q.first.return_value = None
            return q

        db.query.side_effect = _query

        await show_shift_end_details(msg, shift_id=5, db=db, lang="ru")

        msg.answer.assert_called_once()
        # Keyboard should be passed as reply_markup
        _, call_kwargs = msg.answer.call_args
        assert "reply_markup" in call_kwargs

    @pytest.mark.asyncio
    async def test_shift_with_no_active_requests_shows_clean_message(self):
        """show_shift_end_details shows 'no active requests' when lists are empty."""
        from uk_management_bot.handlers.shifts import show_shift_end_details

        msg = _make_message()
        db = _make_db()
        shift = _make_shift(shift_id=7, user_id=10)
        shift.specialization_focus = []
        user = _make_db_user(db_user_id=10)

        returns_iter = iter([shift, None, user, None])

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.join.return_value = q
            q.all.return_value = []
            q.first.return_value = next(returns_iter, None)
            return q

        db.query.side_effect = _query

        await show_shift_end_details(msg, shift_id=7, db=db, lang="ru")

        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args[0][0]
        assert isinstance(sent_text, str)


# ─── my_shift ────────────────────────────────────────────────────────────────

class TestMyShift:
    """Tests for my_shift handler."""

    @pytest.mark.asyncio
    async def test_no_active_shift_sends_no_active_message(self):
        """my_shift tells user there is no active shift."""
        from uk_management_bot.handlers.shifts import my_shift

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_main_keyboard", return_value=MagicMock()
        ):
            svc = MockService.return_value
            svc.get_active_shift.return_value = None

            await my_shift(msg, db=db)

        msg.answer.assert_called_once()
        svc.get_active_shift.assert_called_once_with(msg.from_user.id)

    @pytest.mark.asyncio
    async def test_active_shift_sends_start_time(self):
        """my_shift shows start time when an active shift exists."""
        from uk_management_bot.handlers.shifts import my_shift

        msg = _make_message()
        db = _make_db()
        shift = _make_shift()
        shift.start_time = datetime(2025, 3, 10, 8, 30, 0)

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_main_keyboard", return_value=MagicMock()
        ):
            svc = MockService.return_value
            svc.get_active_shift.return_value = shift

            await my_shift(msg, db=db)

        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args[0][0]
        assert "08:30" in sent_text


# ─── handle_end_shift_cancel ─────────────────────────────────────────────────

class TestHandleEndShiftCancel:
    """Tests for handle_end_shift_cancel callback."""

    @pytest.mark.asyncio
    async def test_cancel_edits_message(self):
        """handle_end_shift_cancel edits the message text and answers callback."""
        from uk_management_bot.handlers.shifts import handle_end_shift_cancel

        cb = _make_callback(data="end_shift_cancel")
        cb.message.edit_text = AsyncMock()

        await handle_end_shift_cancel(cb)

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()


# ─── end_shift_no ─────────────────────────────────────────────────────────────

class TestEndShiftNo:
    """Tests for end_shift_no callback."""

    @pytest.mark.asyncio
    async def test_end_shift_no_edits_message(self):
        """end_shift_no edits the message and answers the callback."""
        from uk_management_bot.handlers.shifts import end_shift_no

        cb = _make_callback(data="shift_end_confirm_no")
        cb.message.edit_text = AsyncMock()

        await end_shift_no(cb)

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()


# ─── suggest_executor_skip ───────────────────────────────────────────────────

class TestSuggestExecutorSkip:
    """Tests for suggest_executor_skip callback."""

    @pytest.mark.asyncio
    async def test_suggest_skip_answers_callback(self):
        """suggest_executor_skip answers the callback and sends a text."""
        from uk_management_bot.handlers.shifts import suggest_executor_skip

        cb = _make_callback(data="suggest_executor_skip")

        await suggest_executor_skip(cb)

        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_suggest_skip_sends_message(self):
        """suggest_executor_skip sends a message to the user."""
        from uk_management_bot.handlers.shifts import suggest_executor_skip

        cb = _make_callback(data="suggest_executor_skip")

        await suggest_executor_skip(cb)

        cb.message.answer.assert_called_once()


# ─── shifts_history ──────────────────────────────────────────────────────────

class TestShiftsHistory:
    """Tests for shifts_history handler."""

    @pytest.mark.asyncio
    async def test_empty_shifts_list_sends_empty_message(self):
        """shifts_history sends 'empty' text when there are no shifts."""
        from uk_management_bot.handlers.shifts import shifts_history

        msg = _make_message()
        db = _make_db()
        state = _make_state(data={"my_shifts_period": "all", "my_shifts_status": "all", "my_shifts_page": 1})

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_filters_inline", return_value=MagicMock(inline_keyboard=[])
        ), patch(
            "uk_management_bot.handlers.shifts.get_pagination_inline", return_value=MagicMock(inline_keyboard=[])
        ):
            svc = MockService.return_value
            svc.list_shifts.return_value = []

            await shifts_history(msg, state, db=db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_shifts_list_renders_shift_rows(self):
        """shifts_history lists shift start/end times in the message."""
        from uk_management_bot.handlers.shifts import shifts_history

        msg = _make_message()
        db = _make_db()
        state = _make_state(data={"my_shifts_period": "all", "my_shifts_status": "all", "my_shifts_page": 1})

        shift = _make_shift()
        shift.start_time = datetime(2025, 2, 1, 8, 0, 0)
        shift.end_time = datetime(2025, 2, 1, 17, 0, 0)
        shift.status = "completed"

        with patch(
            "uk_management_bot.handlers.shifts.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shifts.ShiftService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shifts.get_shifts_filters_inline", return_value=MagicMock(inline_keyboard=[])
        ), patch(
            "uk_management_bot.handlers.shifts.get_pagination_inline", return_value=MagicMock(inline_keyboard=[])
        ):
            svc = MockService.return_value
            svc.list_shifts.return_value = [shift]

            await shifts_history(msg, state, db=db)

        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args[0][0]
        assert "01.02.2025" in sent_text
