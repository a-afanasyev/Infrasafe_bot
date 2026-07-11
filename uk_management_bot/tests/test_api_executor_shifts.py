"""
Unit tests for uk_management_bot/api/shifts/executor_router.py

Tests cover:
- start_shift()        — creates active shift
- end_shift()          — completes active shift; errors on not-found, wrong owner, wrong status
- get_current_shift()  — returns active shift or None
- get_my_shifts()      — returns ordered list
- _shift_out()         — pure helper, ISO timestamps
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


# ── Helpers ─────────────────────────────────────────────────────────


def _make_user(id: int = 1, roles: str = '["executor"]', role: str = "executor"):
    user = MagicMock()
    user.id = id
    user.roles = roles
    user.role = role
    return user


def _make_shift(
    *,
    id: int = 10,
    user_id: int = 1,
    status: str = "active",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    notes: str | None = None,
):
    shift = MagicMock()
    shift.id = id
    shift.user_id = user_id
    shift.status = status
    shift.start_time = start_time or datetime.now(timezone.utc)
    shift.end_time = end_time
    shift.notes = notes
    return shift


# ── start_shift ──────────────────────────────────────────────────────


class TestStartShift:
    @pytest.mark.asyncio
    async def test_creates_active_shift(self):
        from uk_management_bot.api.shifts.executor_router import start_shift, StartShiftBody

        user = _make_user(id=1)
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        created_shift = None

        async def capture_refresh(obj):
            nonlocal created_shift
            created_shift = obj
            # Assign id so _shift_out works
            obj.id = 99
            obj.user_id = 1
            obj.status = "active"
            obj.start_time = datetime.now(timezone.utc)
            obj.end_time = None
            obj.notes = None

        mock_db.refresh = capture_refresh

        body = StartShiftBody(notes=None)
        result = await start_shift(body=body, user=user, db=mock_db)

        assert result.status == "active"
        assert result.user_id == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_shift_with_notes(self):
        from uk_management_bot.api.shifts.executor_router import start_shift, StartShiftBody

        user = _make_user(id=2)
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        async def capture_refresh(obj):
            obj.id = 5
            obj.user_id = 2
            obj.status = "active"
            obj.start_time = datetime.now(timezone.utc)
            obj.end_time = None
            obj.notes = "test note"

        mock_db.refresh = capture_refresh

        body = StartShiftBody(notes="test note")
        result = await start_shift(body=body, user=user, db=mock_db)

        assert result.notes == "test note"

    @pytest.mark.asyncio
    async def test_start_shift_returns_shift_out_schema(self):
        from uk_management_bot.api.shifts.executor_router import start_shift, StartShiftBody, ShiftOut

        user = _make_user(id=3)
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        async def capture_refresh(obj):
            obj.id = 7
            obj.user_id = 3
            obj.status = "active"
            obj.start_time = datetime.now(timezone.utc)
            obj.end_time = None
            obj.notes = None

        mock_db.refresh = capture_refresh

        body = StartShiftBody()
        result = await start_shift(body=body, user=user, db=mock_db)

        assert isinstance(result, ShiftOut)
        assert result.id == 7


# ── end_shift ────────────────────────────────────────────────────────


class TestEndShift:
    @pytest.mark.asyncio
    async def test_ends_active_shift_successfully(self):
        from uk_management_bot.api.shifts.executor_router import end_shift

        user = _make_user(id=1)
        shift = _make_shift(id=10, user_id=1, status="active")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = shift
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        async def capture_refresh(obj):
            # end_time and status already mutated on the shift mock
            pass

        mock_db.refresh = capture_refresh

        result = await end_shift(shift_id=10, user=user, db=mock_db)

        assert result.status == "completed"
        assert shift.end_time is not None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shift_not_found_raises_404(self):
        from fastapi import HTTPException
        from uk_management_bot.api.shifts.executor_router import end_shift

        user = _make_user(id=1)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await end_shift(shift_id=999, user=user, db=mock_db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_owner_raises_403(self):
        from fastapi import HTTPException
        from uk_management_bot.api.shifts.executor_router import end_shift

        user = _make_user(id=1)
        shift = _make_shift(id=10, user_id=2, status="active")  # owned by user 2

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = shift
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await end_shift(shift_id=10, user=user, db=mock_db)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_non_active_shift_raises_409(self):
        from fastapi import HTTPException
        from uk_management_bot.api.shifts.executor_router import end_shift

        user = _make_user(id=1)
        shift = _make_shift(id=10, user_id=1, status="completed")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = shift
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await end_shift(shift_id=10, user=user, db=mock_db)

        assert exc_info.value.status_code == 409
        assert "completed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cancelled_shift_raises_409(self):
        from fastapi import HTTPException
        from uk_management_bot.api.shifts.executor_router import end_shift

        user = _make_user(id=5)
        shift = _make_shift(id=20, user_id=5, status="cancelled")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = shift
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await end_shift(shift_id=20, user=user, db=mock_db)

        assert exc_info.value.status_code == 409


# ── get_current_shift ────────────────────────────────────────────────


class TestGetCurrentShift:
    @pytest.mark.asyncio
    async def test_returns_active_shift_when_present(self):
        from uk_management_bot.api.shifts.executor_router import get_current_shift

        user = _make_user(id=1)
        shift = _make_shift(id=5, user_id=1, status="active")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = shift
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_shift(user=user, db=mock_db)

        assert result is not None
        assert result.id == 5
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_shift(self):
        from uk_management_bot.api.shifts.executor_router import get_current_shift

        user = _make_user(id=1)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_shift(user=user, db=mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_shift_out_fields_populated(self):
        from uk_management_bot.api.shifts.executor_router import get_current_shift, ShiftOut

        user = _make_user(id=1)
        shift = _make_shift(id=7, user_id=1, status="active", notes="morning shift")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = shift
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_shift(user=user, db=mock_db)

        assert isinstance(result, ShiftOut)
        assert result.notes == "morning shift"
        assert result.user_id == 1


# ── get_my_shifts ────────────────────────────────────────────────────


class TestGetMyShifts:
    @pytest.mark.asyncio
    async def test_returns_list_of_shift_outs(self):
        from uk_management_bot.api.shifts.executor_router import get_my_shifts, ShiftOut

        user = _make_user(id=1)
        shifts = [
            _make_shift(id=i, user_id=1, status="completed")
            for i in range(1, 4)
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = shifts
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_shifts(limit=20, user=user, db=mock_db)

        assert len(result) == 3
        assert all(isinstance(s, ShiftOut) for s in result)

    @pytest.mark.asyncio
    async def test_empty_shift_list_returns_empty(self):
        from uk_management_bot.api.shifts.executor_router import get_my_shifts

        user = _make_user(id=1)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_shifts(limit=20, user=user, db=mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_ids_preserved_in_output(self):
        from uk_management_bot.api.shifts.executor_router import get_my_shifts

        user = _make_user(id=1)
        shifts = [_make_shift(id=100 + i, user_id=1) for i in range(5)]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = shifts
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_shifts(limit=20, user=user, db=mock_db)

        assert [s.id for s in result] == [100, 101, 102, 103, 104]


# ── _shift_out helper ────────────────────────────────────────────────


class TestShiftOutHelper:
    def test_shift_with_end_time_serialized(self):
        from uk_management_bot.api.shifts.executor_router import _shift_out

        now = datetime.now(timezone.utc)
        shift = _make_shift(id=1, user_id=1, status="completed", end_time=now)

        result = _shift_out(shift)

        assert result.end_time is not None
        assert result.end_time == now.isoformat()

    def test_shift_without_end_time_is_none(self):
        from uk_management_bot.api.shifts.executor_router import _shift_out

        shift = _make_shift(id=1, user_id=1, status="active", end_time=None)

        result = _shift_out(shift)

        assert result.end_time is None

    def test_start_time_is_iso_string(self):
        from uk_management_bot.api.shifts.executor_router import _shift_out

        ts = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        shift = _make_shift(id=1, user_id=1, start_time=ts)

        result = _shift_out(shift)

        assert "2025-06-15" in result.start_time
        assert "10:30:00" in result.start_time
