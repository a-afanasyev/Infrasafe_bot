"""APIFE-1: readers tolerate several active shifts per executor.

Bot-core intentionally allows one executor to hold multiple active shifts
(multi-specialization — services/shift_service.py). Three API readers previously
used scalar_one_or_none() and raised MultipleResultsFound → 500. They must now
select the freshest active shift deterministically and never raise.
"""
from datetime import datetime, timezone, timedelta

import pytest

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.api.shifts import service
from uk_management_bot.api.shifts.executor_router import get_current_shift

BASE = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)


async def _user(db, tg=2001):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="E", last_name=str(tg),
             roles='["executor"]', status="approved")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _active_shift(db, user_id, *, start, shift_id=None):
    s = Shift(user_id=user_id, status="active", start_time=start)
    if shift_id is not None:
        s.id = shift_id
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.mark.asyncio
async def test_get_current_shift_returns_freshest_of_multiple(db_session):
    user = await _user(db_session)
    await _active_shift(db_session, user.id, start=BASE)
    fresh = await _active_shift(db_session, user.id, start=BASE + timedelta(hours=2))

    result = await get_current_shift(user=user, db=db_session)

    assert result is not None
    assert result.id == fresh.id  # most recent start_time wins, no 500


@pytest.mark.asyncio
async def test_get_current_shift_tiebreak_by_id(db_session):
    user = await _user(db_session, tg=2002)
    a = await _active_shift(db_session, user.id, start=BASE)
    b = await _active_shift(db_session, user.id, start=BASE)  # same start_time

    result = await get_current_shift(user=user, db=db_session)

    assert result is not None
    assert result.id == max(a.id, b.id)  # deterministic tie-break: larger id


@pytest.mark.asyncio
async def test_get_employee_with_stats_survives_multiple_active(db_session):
    user = await _user(db_session, tg=2003)
    await _active_shift(db_session, user.id, start=BASE)
    fresh = await _active_shift(db_session, user.id, start=BASE + timedelta(hours=3))

    row = await service.get_employee_with_stats(db_session, user.id)

    assert row is not None
    emp, active_shift, total_shifts, _completed, _rating = row
    assert emp.id == user.id
    assert active_shift is not None
    assert active_shift.id == fresh.id  # freshest, not MultipleResultsFound
    assert total_shifts == 2            # aggregate tolerates multiplicity


@pytest.mark.asyncio
async def test_find_overlapping_returns_single_row_not_raises(db_session):
    user = await _user(db_session, tg=2004)
    # two bounded shifts both overlapping the probe window
    win_start = BASE
    win_end = BASE + timedelta(hours=8)
    for offset in (0, 1):
        s = Shift(
            user_id=user.id, status="active",
            start_time=win_start + timedelta(hours=offset),
            end_time=win_end + timedelta(hours=offset),
        )
        db_session.add(s)
    await db_session.commit()

    overlap = await service.find_overlapping_shift_for_update(
        db_session, user_id=user.id,
        start_time=win_start + timedelta(hours=2),
        end_time=win_start + timedelta(hours=4),
        lock=False,  # sqlite: no row-lock semantics asserted
    )

    assert overlap is not None  # existence, not MultipleResultsFound
