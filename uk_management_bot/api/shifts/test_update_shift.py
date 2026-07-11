"""
Unit tests for update_shift() in api/shifts/router.py.

Cover the editing logic added for the dashboard "edit shift" feature:
- planned_start_time/planned_end_time stay in sync when actual times change
- priority_level / specialization_focus are applied
- content edits are rejected (409) on terminal (completed/cancelled) shifts
- end_time must be after start_time (422)

Endpoint functions are called directly with a mocked AsyncSession (same style
as tests/test_api_executor_shifts.py). _shift_detail / publish_shift_event are
patched out so the test focuses on the mutation logic.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.api.shifts.schemas import UpdateShiftBody


def _make_user(id: int = 1):
    user = MagicMock()
    user.id = id
    user.roles = '["manager"]'
    user.role = "manager"
    return user


def _make_shift(*, status: str = "planned", start_time=None, end_time=None):
    base = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    shift = MagicMock()
    shift.id = 67
    shift.user_id = 1
    shift.status = status
    shift.start_time = start_time or base
    shift.end_time = end_time if end_time is not None else base + timedelta(hours=24)
    shift.planned_start_time = None
    shift.planned_end_time = None
    return shift


def _mock_db(shift, overlap=None):
    """First execute() returns the shift; later ones (overlap check) return
    `overlap` (None = no conflict)."""
    db = AsyncMock()
    fetch_result = MagicMock()
    fetch_result.scalar_one_or_none.return_value = shift
    overlap_result = MagicMock()
    # APIFE-1: find_overlapping_shift_for_update now reads via .scalars().first()
    # (tolerant of multiple overlaps) instead of scalar_one_or_none().
    overlap_result.scalars.return_value.first.return_value = overlap
    pending = [fetch_result]

    async def execute(*_a, **_k):
        return pending.pop(0) if pending else overlap_result

    db.execute = execute
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


async def _call(shift, body, overlap=None):
    from uk_management_bot.api.shifts import router as shift_router
    with patch.object(shift_router, "_shift_detail", return_value=MagicMock()), \
         patch.object(shift_router, "publish_shift_event", new=AsyncMock()):
        return await shift_router.update_shift(
            shift_id=shift.id, body=body, db=_mock_db(shift, overlap), _user=_make_user()
        )


class TestUpdateShiftTimeSync:
    @pytest.mark.asyncio
    async def test_planned_times_sync_when_actual_times_change(self):
        new_start = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)
        shift = _make_shift(status="planned")
        await _call(shift, UpdateShiftBody(start_time=new_start, end_time=new_end))
        assert shift.start_time == new_start
        assert shift.end_time == new_end
        # bot schedule reads planned_*; must mirror the new actual times
        assert shift.planned_start_time == new_start
        assert shift.planned_end_time == new_end

    @pytest.mark.asyncio
    async def test_planned_end_not_touched_when_only_start_changes(self):
        new_start = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        shift = _make_shift(status="active")
        shift.end_time = None  # open-ended active shift; no end to validate against
        await _call(shift, UpdateShiftBody(start_time=new_start))
        assert shift.planned_start_time == new_start
        # end_time was not in the payload → planned_end_time stays untouched
        assert shift.planned_end_time is None


class TestUpdateShiftFields:
    @pytest.mark.asyncio
    async def test_priority_and_specializations_applied(self):
        shift = _make_shift(status="planned")
        await _call(
            shift,
            UpdateShiftBody(priority_level=4, specialization_focus=["electrician"]),
        )
        assert shift.priority_level == 4
        assert shift.specialization_focus == ["electrician"]


class TestUpdateShiftGuards:
    @pytest.mark.asyncio
    async def test_content_edit_on_completed_shift_raises_409(self):
        from fastapi import HTTPException
        shift = _make_shift(status="completed")
        with pytest.raises(HTTPException) as exc:
            await _call(shift, UpdateShiftBody(notes="late note"))
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_content_edit_on_cancelled_shift_raises_409(self):
        from fastapi import HTTPException
        shift = _make_shift(status="cancelled")
        with pytest.raises(HTTPException) as exc:
            await _call(shift, UpdateShiftBody(max_requests=5))
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_end_before_start_raises_422(self):
        from fastapi import HTTPException
        start = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
        shift = _make_shift(status="planned", start_time=start)
        bad_end = datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc)
        with pytest.raises(HTTPException) as exc:
            await _call(shift, UpdateShiftBody(end_time=bad_end))
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_overlapping_shift_on_time_change_raises_409(self):
        from fastapi import HTTPException
        new_start = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 6, 10, 18, 0, tzinfo=timezone.utc)
        shift = _make_shift(status="planned")
        with pytest.raises(HTTPException) as exc:
            await _call(
                shift,
                UpdateShiftBody(start_time=new_start, end_time=new_end),
                overlap=MagicMock(),  # a conflicting shift exists
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_naive_datetimes_are_accepted_and_synced(self):
        # tz-naive input (client omitted the offset) must not 500.
        new_start = datetime(2026, 6, 10, 9, 0)
        new_end = datetime(2026, 6, 10, 18, 0)
        shift = _make_shift(status="planned")
        await _call(shift, UpdateShiftBody(start_time=new_start, end_time=new_end))
        assert shift.planned_start_time.tzinfo is not None
        assert shift.planned_end_time.tzinfo is not None
