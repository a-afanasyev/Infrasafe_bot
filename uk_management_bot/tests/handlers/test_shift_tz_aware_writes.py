"""AUD5-CODE-3: naive datetime writes to timestamptz Shift columns.

`handle_start_shift`/`handle_end_shift` (my_shifts.py) and the select-shift
end path (shifts.py) wrote `datetime.now()` (naive) into `Shift.start_time`/
`end_time` (`DateTime(timezone=True)`), and derived duration via
`.replace(tzinfo=None)` strip-workarounds instead of aware arithmetic. A
shift with an aware +05:00 start_time (Tashkent) exposed the bug: the strip
discarded the offset and treated the wall-clock as if it were UTC, skewing
duration by the offset (5h here) instead of the real elapsed time (~2h).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_callback():
    cb = MagicMock()
    cb.from_user.id = 123456789
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(shift_id=42):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"current_shift_id": shift_id})
    state.set_state = AsyncMock()
    return state


def _make_user(user_id=7):
    user = MagicMock()
    user.id = user_id
    return user


def _make_db_returning(shift):
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = shift
    db = MagicMock()
    db.query.return_value = query
    db.commit = MagicMock()
    return db


class TestStartShiftWritesAwareStartTime:
    @pytest.mark.asyncio
    async def test_start_shift_writes_aware_start_time(self):
        from uk_management_bot.handlers.my_shifts import handle_start_shift

        shift = MagicMock()
        shift.status = "planned"
        shift.current_request_count = 0
        db = _make_db_returning(shift)

        with patch(
            "uk_management_bot.handlers.my_shifts.get_shift_actions_keyboard",
            return_value=MagicMock(),
        ):
            await handle_start_shift(
                _make_callback(),
                _make_state(),
                language="ru",
                db=db,
                user=_make_user(),
                roles=["executor"],
            )

        assert shift.start_time.tzinfo is not None
        assert shift.start_time.utcoffset() == timedelta(0)


class TestEndShiftWritesAwareEndTimeAndDuration:
    @pytest.mark.asyncio
    async def test_end_shift_writes_aware_end_time_and_correct_duration(self):
        from uk_management_bot.handlers.my_shifts import handle_end_shift

        tashkent = timezone(timedelta(hours=5))
        # 2 real elapsed hours ago, expressed in +05:00 wall-clock.
        shift_start_aware = (datetime.now(timezone.utc) - timedelta(hours=2)).astimezone(tashkent)

        shift = MagicMock()
        shift.status = "active"
        shift.start_time = shift_start_aware
        shift.current_request_count = 0
        db = _make_db_returning(shift)
        callback = _make_callback()

        await handle_end_shift(
            callback,
            _make_state(),
            language="ru",
            db=db,
            user=_make_user(),
            roles=["executor"],
        )

        assert shift.end_time.tzinfo is not None
        assert shift.end_time.utcoffset() == timedelta(0)

        # duration ≈ 2h (old naive-strip code did `naive_now - start.replace(tzinfo=None)`,
        # discarding the +05:00 offset and comparing against the wrong wall-clock
        # instant — it would have reported a wrong value, here ≈ -3h, not the real ≈2h).
        edit_args = callback.message.edit_text.await_args
        rendered_text = edit_args.args[0] if edit_args.args else edit_args.kwargs.get("text", "")
        assert "2.0 ч" in rendered_text or "2.1 ч" in rendered_text, rendered_text


class TestShiftsPySelectEndWritesAwareEndTime:
    @pytest.mark.asyncio
    async def test_end_shift_select_writes_aware_end_time(self):
        from uk_management_bot.handlers import shifts as shifts_module
        from uk_management_bot.database.models.user import User as UserModel
        from uk_management_bot.database.models.shift import Shift as ShiftModel

        user = _make_user()
        user.telegram_id = 123456789
        user.language = "ru"

        shift = MagicMock()
        shift.status = "active"
        shift.user_id = user.id
        shift.id = 1
        shift.specialization_focus = None
        shift.start_time = datetime.now(timezone.utc) - timedelta(hours=2)

        db = MagicMock()

        def _query(model):
            q = MagicMock()
            if model is UserModel:
                q.filter.return_value.first.return_value = user
            elif model is ShiftModel:
                q.filter.return_value.first.return_value = shift
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _query
        db.commit = MagicMock()
        db.add = MagicMock()

        callback = _make_callback()
        callback.data = "shift_end_confirm_yes:1"

        with patch.object(shifts_module, "session_scope") as mock_scope:
            mock_scope.return_value.__enter__.return_value = db
            mock_scope.return_value.__exit__.return_value = False
            await shifts_module.end_shift_yes_with_id(callback, language="ru")

        assert shift.end_time.tzinfo is not None
        assert shift.end_time.utcoffset() == timedelta(0)
