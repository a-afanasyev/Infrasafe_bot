"""Генерация заданий дня и закрытие дня модуля «Уборка» (семантика; sqlite)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningDay,
    CleaningPlanVersion,
    CleaningRules,
    CleaningTask,
    CleaningTaskEvent,
)
from uk_management_bot.services.cleaning import days
from uk_management_bot.services.cleaning.transitions import TransitionError, move
from uk_management_bot.utils.business_time import business_wall_clock

TUE = date(2026, 11, 17)  # вторник
WET_1_5 = {"work_kind": "wet", "weekdays": [0, 3], "floor_from": 1, "floor_to": 5}
WET_6_9 = {"work_kind": "wet", "weekdays": [1, 4], "floor_from": 6, "floor_to": 9}
DRY_ALL_TUE = {"work_kind": "dry", "weekdays": [1]}


def _version(building_id=1, *, valid_from, valid_to=None, items=(WET_1_5, WET_6_9), entrances=2):
    return CleaningPlanVersion(
        building_id=building_id, valid_from=valid_from, valid_to=valid_to, items=list(items),
        extra_points=[], floor_count=9, entrance_count=entrances,
    )


def _noon(day: date) -> datetime:
    return business_wall_clock(day, 12)


@pytest.fixture
async def db(el_async_factory, el_seed):
    async with el_async_factory() as session:
        session.add_all([el_seed.yard(), el_seed.building(1, entrance_count=2),
                         el_seed.user(11), el_seed.user(12)])
        await session.commit()
        yield session


async def _tasks(db) -> list[CleaningTask]:
    rows = await db.execute(select(CleaningTask).order_by(CleaningTask.work_date, CleaningTask.entrance))
    return list(rows.scalars())


async def test_tasks_are_generated_from_plan_and_assignment(db):
    db.add_all([
        _version(valid_from=date(2026, 11, 1)),
        CleaningAssignment(building_id=1, entrance=1, user_id=11, valid_from=date(2026, 11, 1)),
    ])
    await db.flush()

    await days.ensure_tasks(db, TUE, now=_noon(TUE))

    first, second = await _tasks(db)
    assert (first.entrance, first.responsible_id, first.status) == (1, 11, "planned")
    assert first.works == ["wet"]
    assert first.slots_required == ["floor:6", "floor:7", "floor:8", "floor:9"]
    assert (second.entrance, second.responsible_id) == (2, None)  # подъезд без назначения


async def test_generation_is_idempotent(db):
    db.add(_version(valid_from=date(2026, 11, 1)))
    await db.flush()
    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    assert len(await _tasks(db)) == 2


async def test_past_day_is_restored_from_the_version_valid_then(db):
    """Правка плана до восстановления пропущенной генерации не меняет прошлый день."""
    db.add_all([
        _version(valid_from=date(2026, 11, 1), valid_to=TUE),
        _version(valid_from=TUE + timedelta(days=1), items=(DRY_ALL_TUE,)),
        CleaningAssignment(building_id=1, entrance=1, user_id=11, valid_from=date(2026, 11, 1), valid_to=TUE),
        CleaningAssignment(building_id=1, entrance=1, user_id=12, valid_from=TUE + timedelta(days=1)),
    ])
    await db.flush()

    await days.ensure_tasks(db, TUE, now=_noon(TUE + timedelta(days=1)))

    task = (await _tasks(db))[0]
    assert task.works == ["wet"] and task.slots_required[0] == "floor:6"
    assert task.responsible_id == 11


async def test_day_without_work_or_inactive_building_gets_no_tasks(db, el_seed):
    db.add_all([el_seed.building(2, address="д. 7", is_active=False),
                _version(valid_from=date(2026, 11, 1)),
                _version(2, valid_from=date(2026, 11, 1), items=(DRY_ALL_TUE,))])
    await db.flush()
    sunday = date(2026, 11, 22)
    await days.ensure_tasks(db, sunday, now=_noon(sunday))
    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    assert {(t.building_id, t.work_date) for t in await _tasks(db)} == {(1, TUE)}


async def test_days_older_than_backfill_are_skipped(db):
    db.add(_version(valid_from=date(2026, 11, 1)))
    await db.flush()
    await days.ensure_tasks(db, TUE, now=_noon(TUE + timedelta(days=4)))
    day = await db.get(CleaningDay, TUE)
    assert day.skipped is True and await _tasks(db) == []


async def test_day_end_comes_from_rules_effective_before_that_day(db):
    before = business_wall_clock(TUE - timedelta(days=1), 10)
    during = business_wall_clock(TUE, 9)
    db.add_all([
        CleaningRules(id=1, data={"day_end_time": "20:00"}, created_at=before),
        CleaningRules(id=2, data={"day_end_time": "18:00"}, created_at=during),  # действует с завтра
    ])
    await db.flush()

    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    await days.ensure_tasks(db, TUE + timedelta(days=1), now=_noon(TUE + timedelta(days=1)))

    today, tomorrow = await db.get(CleaningDay, TUE), await db.get(CleaningDay, TUE + timedelta(days=1))
    assert today.day_end_at.replace(tzinfo=timezone.utc) == business_wall_clock(TUE, 20)
    assert today.rules_version == 1
    assert tomorrow.day_end_at.replace(tzinfo=timezone.utc) == business_wall_clock(TUE + timedelta(days=1), 18)


async def test_default_day_end_is_2359(db):
    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    day = await db.get(CleaningDay, TUE)
    assert day.day_end_at.replace(tzinfo=timezone.utc) == business_wall_clock(TUE, 23, 59)
    assert day.rules_version is None


async def test_day_closes_only_after_grace_and_marks_missed_and_expired(db):
    db.add(_version(valid_from=date(2026, 11, 1)))
    await db.flush()
    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    started = (await _tasks(db))[0]
    await move(db, started, "in_progress", kind="first_photo")
    end = business_wall_clock(TUE, 23, 59)

    await days.close_days(db, now=end + timedelta(minutes=4))
    assert (await db.get(CleaningDay, TUE)).closed_at is None

    await days.close_days(db, now=end + timedelta(minutes=6))
    await days.close_days(db, now=end + timedelta(minutes=30))  # повтор безопасен

    first, second = await _tasks(db)
    assert (first.status, second.status) == ("expired", "missed")
    assert (await db.get(CleaningDay, TUE)).closed_at is not None
    kinds = (await db.execute(select(CleaningTaskEvent.kind).order_by(CleaningTaskEvent.id))).scalars().all()
    assert kinds == ["first_photo", "day_closed", "day_closed"]


async def test_tick_backfills_missed_days_and_closes_them(db):
    db.add(_version(valid_from=date(2026, 11, 1)))
    await db.flush()
    await days.tick(db, now=_noon(TUE + timedelta(days=2)))
    by_day = {}
    for task in await _tasks(db):
        by_day.setdefault(task.work_date, set()).add(task.status)
    assert by_day[TUE] == {"missed"}                         # пропущенный день восстановлен и закрыт
    assert by_day[TUE + timedelta(days=2)] == {"planned"}   # сегодняшний открыт


async def test_transition_table_rejects_unknown_moves_and_bumps_version(db):
    db.add(_version(valid_from=date(2026, 11, 1)))
    await db.flush()
    await days.ensure_tasks(db, TUE, now=_noon(TUE))
    task = (await _tasks(db))[0]
    with pytest.raises(TransitionError):
        await move(db, task, "accepted", kind="manual")  # planned → accepted запрещён
    await move(db, task, "in_progress", kind="first_photo")
    assert (task.status, task.version) == ("in_progress", 2)
