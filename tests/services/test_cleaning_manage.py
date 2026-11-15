"""Версии плана дома, назначения подъездов и нагрузка по этажам (этап 2, sqlite)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.cleaning import CleaningAssignment, CleaningPlanVersion
from uk_management_bot.services.cleaning import assignments, days, load, plans
from uk_management_bot.services.cleaning.planning import PlanError, parse_items
from uk_management_bot.utils.business_time import business_wall_clock

MON = date(2026, 11, 16)
TUE, WED = MON + timedelta(days=1), MON + timedelta(days=2)
MANAGER, CLEANER, CLEANER2, PLUMBER = 1, 11, 12, 13
WET = [{"work_kind": "wet", "weekdays": [0, 2, 4]}]                      # все этажи
SPLIT = [{"work_kind": "wet", "weekdays": [0, 3], "floor_from": 1, "floor_to": 5},
         {"work_kind": "wet", "weekdays": [1, 4], "floor_from": 6, "floor_to": 9}]


def _at(day: date, hour: int = 12):
    return business_wall_clock(day, hour)


@pytest.fixture
async def db(el_async_factory, el_seed):
    async with el_async_factory() as session:
        staff = dict(roles='["executor"]')
        session.add_all([
            el_seed.yard(), el_seed.building(1, entrance_count=3), el_seed.building(2, address="д. 7", entrance_count=1),
            el_seed.user(MANAGER, roles='["manager"]'),
            el_seed.user(CLEANER, specialization="cleaning", **staff),
            el_seed.user(CLEANER2, specialization="cleaning", **staff),
            el_seed.user(PLUMBER, specialization="plumber", **staff),
        ])
        await session.commit()
        yield session


async def _versions(db, building_id=1):
    return list((await db.execute(
        select(CleaningPlanVersion).where(CleaningPlanVersion.building_id == building_id)
        .order_by(CleaningPlanVersion.valid_from))).scalars())


async def _assigned(db, day, building_id=1):
    rows = (await db.execute(select(CleaningAssignment).where(CleaningAssignment.building_id == building_id))).scalars()
    return {a.entrance: a.user_id for a in rows
            if a.valid_from <= day and (a.valid_to is None or a.valid_to >= day)}


# ── версии плана ────────────────────────────────────────────────────────────

async def test_first_save_creates_version_effective_tomorrow_with_building_snapshot(db):
    version = await plans.save_plan(db, building_id=1, items=WET, extra_points=["entrance"],
                                    actor_id=MANAGER, now=_at(MON))
    assert (version.valid_from, version.valid_to) == (TUE, None)
    assert (version.floor_count, version.entrance_count, version.extra_points) == (9, 3, ["entrance"])


async def test_edit_closes_running_version_and_today_keeps_the_old_plan(db):
    await plans.save_plan(db, building_id=1, items=WET, extra_points=[], actor_id=MANAGER, now=_at(MON - timedelta(days=5)))
    await plans.save_plan(db, building_id=1, items=SPLIT, extra_points=[], actor_id=MANAGER, now=_at(MON))
    old, new = await _versions(db)
    assert (old.valid_to, new.valid_from) == (MON, TUE)

    await days.ensure_tasks(db, MON, now=_at(MON, 13))  # сгенерировано ПОСЛЕ правки
    await days.ensure_tasks(db, TUE, now=_at(TUE))
    today, tomorrow = (await plans.tasks_of(db, 1, MON))[0], (await plans.tasks_of(db, 1, TUE))[0]
    assert len(today.slots_required) == 9 and tomorrow.slots_required == ["floor:6", "floor:7", "floor:8", "floor:9"]


async def test_second_edit_on_the_same_day_replaces_the_not_yet_started_version(db):
    await plans.save_plan(db, building_id=1, items=WET, extra_points=[], actor_id=MANAGER, now=_at(MON, 9))
    await plans.save_plan(db, building_id=1, items=SPLIT, extra_points=[], actor_id=MANAGER, now=_at(MON, 15))
    (only,) = await _versions(db)
    assert only.valid_from == TUE and only.items == SPLIT


@pytest.mark.parametrize("items, points, code", [
    ([{"work_kind": "wet", "weekdays": [0], "floor_from": 1, "floor_to": 12}], [], "bad_floors"),
    (WET, ["Entrance!"], "bad_extra_points"),
    ([], [], "empty_plan"),
])
async def test_invalid_plan_is_rejected(db, items, points, code):
    with pytest.raises(PlanError) as exc:
        await plans.save_plan(db, building_id=1, items=items, extra_points=points, actor_id=MANAGER, now=_at(MON))
    assert exc.value.code == code and await _versions(db) == []


async def test_plan_view_reports_current_upcoming_coverage_and_snapshot_mismatch(db):
    await plans.save_plan(db, building_id=1, items=WET, extra_points=[], actor_id=MANAGER, now=_at(MON - timedelta(days=5)))
    await plans.save_plan(db, building_id=1, items=SPLIT[:1], extra_points=[], actor_id=MANAGER, now=_at(MON))
    view = await plans.plan_view(db, 1, now=_at(MON))
    assert view.current.items == WET and view.upcoming.items == SPLIT[:1]
    assert view.uncovered == {"wet": [6, 7, 8, 9]}  # в новой версии верхние этажи не моются
    assert view.snapshot_mismatch is False

    building = await db.get(plans.Building, 1)
    building.floor_count = 12
    await db.flush()
    assert (await plans.plan_view(db, 1, now=_at(MON))).snapshot_mismatch is True


# ── назначения ──────────────────────────────────────────────────────────────

async def test_assigning_a_building_covers_all_entrances_from_tomorrow(db):
    await assignments.assign(db, building_id=1, entrances=None, user_id=CLEANER, actor_id=MANAGER, now=_at(MON))
    assert await _assigned(db, MON) == {}
    assert await _assigned(db, TUE) == {1: CLEANER, 2: CLEANER, 3: CLEANER}


async def test_reassigning_one_entrance_keeps_history_and_the_rest(db):
    await assignments.assign(db, building_id=1, entrances=None, user_id=CLEANER, actor_id=MANAGER, now=_at(MON - timedelta(days=5)))
    await assignments.assign(db, building_id=1, entrances=[3], user_id=CLEANER2, actor_id=MANAGER, now=_at(MON))
    assert await _assigned(db, MON) == {1: CLEANER, 2: CLEANER, 3: CLEANER}   # вчерашнее не тронуто
    assert await _assigned(db, TUE) == {1: CLEANER, 2: CLEANER, 3: CLEANER2}


async def test_unassign_and_repeat_on_the_same_day_leave_no_overlaps(db):
    await assignments.assign(db, building_id=1, entrances=[1], user_id=CLEANER, actor_id=MANAGER, now=_at(MON, 9))
    await assignments.assign(db, building_id=1, entrances=[1], user_id=CLEANER2, actor_id=MANAGER, now=_at(MON, 10))
    await assignments.assign(db, building_id=1, entrances=[1], user_id=None, actor_id=MANAGER, now=_at(MON, 11))
    assert await _assigned(db, TUE) == {}
    assert (await db.execute(select(CleaningAssignment))).scalars().all() == []  # не начавшиеся удалены


@pytest.mark.parametrize("kwargs, code", [
    (dict(user_id=PLUMBER, entrances=None), "not_a_cleaner"),
    (dict(user_id=999, entrances=None), "not_a_cleaner"),
    (dict(user_id=CLEANER, entrances=[4]), "bad_entrances"),
    (dict(user_id=CLEANER, entrances=[]), "bad_entrances"),
])
async def test_invalid_assignment_is_rejected(db, kwargs, code):
    with pytest.raises(assignments.AssignmentError) as exc:
        await assignments.assign(db, building_id=1, actor_id=MANAGER, now=_at(MON), **kwargs)
    assert exc.value.code == code


# ── нагрузка ────────────────────────────────────────────────────────────────

def test_floors_per_weekday_counts_floor_slots_only():
    items = parse_items(SPLIT + [{"work_kind": "elevator", "weekdays": [0, 1, 2]}], floor_count=9, entrance_count=3)
    assert load.floors_per_weekday(items, entrance=1) == [5, 4, 0, 5, 4, 0, 0]


async def test_load_sums_floors_by_cleaner_and_flags_overload(db):
    yesterday = _at(MON - timedelta(days=1))
    await plans.save_plan(db, building_id=1, items=WET, extra_points=[], actor_id=MANAGER, now=yesterday)      # 3×9
    await plans.save_plan(db, building_id=2, items=SPLIT, extra_points=[], actor_id=MANAGER, now=yesterday)    # 1 подъезд
    await assignments.assign(db, building_id=1, entrances=[1, 2], user_id=CLEANER, actor_id=MANAGER, now=yesterday)
    await assignments.assign(db, building_id=1, entrances=[3], user_id=CLEANER2, actor_id=MANAGER, now=yesterday)
    await assignments.assign(db, building_id=2, entrances=None, user_id=CLEANER, actor_id=MANAGER, now=yesterday)

    report = await load.report(db, day=MON, norm=20)

    first, second = report.cleaners[CLEANER], report.cleaners[CLEANER2]
    assert first.by_weekday == [23, 4, 18, 5, 22, 0, 0] and first.week == 72
    assert (first.peak, first.percent, first.overloaded) == (23, 115, True)
    assert first.buildings == {1: [18, 0, 18, 0, 18, 0, 0], 2: [5, 4, 0, 5, 4, 0, 0]}
    assert (second.by_weekday[0], second.percent, second.overloaded) == (9, 45, False)
    assert report.unassigned == []


async def test_load_reports_entrances_with_plan_but_without_cleaner(db):
    await plans.save_plan(db, building_id=1, items=WET, extra_points=[], actor_id=MANAGER, now=_at(MON - timedelta(days=1)))
    await assignments.assign(db, building_id=1, entrances=[1], user_id=CLEANER, actor_id=MANAGER, now=_at(MON - timedelta(days=1)))
    report = await load.report(db, day=MON, norm=40)
    assert report.unassigned == [(1, 2), (1, 3)]
