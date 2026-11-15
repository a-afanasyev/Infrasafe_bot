"""Контроль менеджера: решения по заданию, замена на день, табель, правила сходства и скорости."""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
    CleaningTaskEvent,
)
from uk_management_bot.services.cleaning import acceptance, complaints, control, days
from uk_management_bot.services.cleaning.rules import rules_for
from uk_management_bot.utils.business_time import business_wall_clock

TUE = date(2026, 11, 17)
NOON = business_wall_clock(TUE, 12)
MANAGER, CLEANER, CLEANER2, RESIDENT = 1, 11, 12, 21


@pytest.fixture
async def db(el_async_factory, el_seed):
    async with el_async_factory() as session:
        staff = dict(roles='["executor"]', specialization="cleaning")
        session.add_all([
            el_seed.yard(), el_seed.building(1, entrance_count=2), el_seed.user(MANAGER, roles='["manager"]'),
            el_seed.user(CLEANER, **staff), el_seed.user(CLEANER2, **staff), el_seed.user(RESIDENT),
            CleaningPlanVersion(building_id=1, valid_from=date(2026, 11, 1), extra_points=[], floor_count=9,
                                entrance_count=2,
                                items=[{"work_kind": "wet", "weekdays": list(range(7)), "floor_from": 1, "floor_to": 2}]),
            CleaningAssignment(building_id=1, entrance=1, user_id=CLEANER, valid_from=date(2026, 11, 1)),
            CleaningAssignment(building_id=1, entrance=2, user_id=CLEANER2, valid_from=date(2026, 11, 1)),
        ])
        await session.flush()
        for day in (TUE - timedelta(days=1), TUE):
            await days.ensure_tasks(session, day, now=business_wall_clock(day, 12))
        await session.commit()
        yield session


async def _task(db, entrance=1, day=TUE) -> CleaningTask:
    return (await db.execute(select(CleaningTask).where(
        CleaningTask.entrance == entrance, CleaningTask.work_date == day))).scalar_one()


async def _set(db, task, status):
    task.status = status
    await db.flush()


def _photo(task, slot, *, at=NOON, dhash="00000000000000ff", sha=None, trust="live"):
    return CleaningPhoto(
        task_id=task.id, slot=slot, op_key=str(uuid.uuid4()), uploaded_by=task.responsible_id,
        upload_sha256=sha or uuid.uuid4().hex * 2, pixel_sha256=sha or uuid.uuid4().hex * 2, dhash=dhash,
        state="done", outcome="activated", is_current=True, trust_level=trust, received_at=at,
        client_captured_at=at, activated_at=at)


# ── решения ─────────────────────────────────────────────────────────────────

async def test_review_decision_needs_fresh_version_and_comment_on_reject(db):
    task = await _task(db)
    await _set(db, task, "review")
    with pytest.raises(control.ControlError) as stale:
        await control.decide(db, task.id, to="accepted", actor_id=MANAGER, version=task.version + 5, now=NOON)
    with pytest.raises(control.ControlError) as silent:
        await control.decide(db, task.id, to="rejected", actor_id=MANAGER, version=task.version, now=NOON)
    assert (stale.value.code, silent.value.code) == ("stale", "comment_required")

    await control.decide(db, task.id, to="rejected", actor_id=MANAGER, version=task.version,
                         comment="фото с экрана", now=NOON)
    event = (await db.execute(select(CleaningTaskEvent).order_by(CleaningTaskEvent.id.desc()))).scalars().first()
    assert task.status == "rejected"
    assert (event.kind, event.actor_id, event.reason, event.to_status) == ("decision", MANAGER, "фото с экрана", "rejected")


@pytest.mark.parametrize("status", ["missed", "expired", "rejected"])
async def test_manual_accept_of_closed_task_requires_comment(db, status):
    task = await _task(db)
    await _set(db, task, status)
    with pytest.raises(control.ControlError) as exc:
        await control.decide(db, task.id, to="accepted", actor_id=MANAGER, version=task.version, now=NOON)
    assert exc.value.code == "comment_required"
    await control.decide(db, task.id, to="accepted", actor_id=MANAGER, version=task.version,
                         comment="убрано, проверил обходом", now=NOON)
    assert task.status == "accepted"


async def test_return_for_retake_only_on_the_task_day_and_forbidden_moves(db):
    today, yesterday = await _task(db), await _task(db, day=TUE - timedelta(days=1))
    await _set(db, today, "review")
    await _set(db, yesterday, "review")
    await control.decide(db, today.id, to="in_progress", actor_id=MANAGER, version=today.version, now=NOON)
    assert today.status == "in_progress"
    with pytest.raises(control.ControlError) as late:
        await control.decide(db, yesterday.id, to="in_progress", actor_id=MANAGER, version=yesterday.version, now=NOON)
    with pytest.raises(control.ControlError) as bad:
        await control.decide(db, today.id, to="rejected", actor_id=MANAGER, version=today.version, comment="x", now=NOON)
    assert (late.value.code, bad.value.code) == ("day_over", "bad_transition")


async def test_same_day_replacement_changes_responsible_with_event(db):
    task = await _task(db)
    await control.reassign(db, task.id, user_id=CLEANER2, actor_id=MANAGER)
    event = (await db.execute(select(CleaningTaskEvent).order_by(CleaningTaskEvent.id.desc()))).scalars().first()
    assert task.responsible_id == CLEANER2 and (event.kind, event.payload) == ("reassigned", {"from": CLEANER, "to": CLEANER2})
    await _set(db, task, "accepted")
    with pytest.raises(control.ControlError) as exc:
        await control.reassign(db, task.id, user_id=CLEANER, actor_id=MANAGER)
    assert exc.value.code == "bad_status"
    with pytest.raises(control.ControlError) as who:
        await control.reassign(db, (await _task(db, entrance=2)).id, user_id=RESIDENT, actor_id=MANAGER)
    assert who.value.code == "not_a_cleaner"


# ── карточка, табель, жалобы ────────────────────────────────────────────────

async def test_card_groups_photos_and_lists_events_and_complaints(db):
    task = await _task(db)
    await _set(db, task, "accepted")
    db.add_all([_photo(task, "floor:1"),
                CleaningPhoto(task_id=task.id, slot="floor:2", op_key=str(uuid.uuid4()), uploaded_by=CLEANER,
                              upload_sha256="1" * 64, state="done", outcome="evidence", trust_level="late",
                              received_at=NOON)])
    await complaints.file_complaint(db, author_id=RESIDENT, building_id=1, entrance=1, work_date=TUE)
    await db.flush()

    card = await control.card(db, task.id)
    assert [p.slot for p in card.current] == ["floor:1"] and [p.slot for p in card.evidence] == ["floor:2"]
    assert card.task.status == "review" and [e.kind for e in card.events] == ["complaint"]
    assert len(card.complaints) == 1 and card.address == "ул. Мира, д. 5"


async def test_timesheet_counts_by_responsible_and_complaints(db):
    await _set(db, await _task(db), "accepted")
    await _set(db, await _task(db, day=TUE - timedelta(days=1)), "expired")
    await _set(db, await _task(db, entrance=2), "rejected")
    complaint = await complaints.file_complaint(db, author_id=RESIDENT, building_id=1, entrance=2, work_date=TUE)
    await complaints.decide(db, complaint.id, outcome="confirmed", actor_id=MANAGER, now=NOON)

    rows = {r.user_id: r for r in await control.timesheet(db, TUE - timedelta(days=1), TUE)}
    first, second = rows[CLEANER], rows[CLEANER2]
    assert (first.planned, first.accepted, first.expired, first.percent) == (2, 1, 1, 50)
    assert (second.planned, second.rejected, second.missed, second.complaints, second.confirmed) == (2, 1, 0, 1, 1)


# ── правила автоприёмки этапа 4 ─────────────────────────────────────────────

async def _reasons(db, task, monkeypatch):
    async def not_on_probation(*args, **kwargs):
        return False
    monkeypatch.setattr(acceptance, "on_probation", not_on_probation)
    monkeypatch.setattr(acceptance, "pick_sampled", lambda rules: False)
    return (await acceptance.evaluate(db, task, await rules_for(db, task.work_date))).reasons


async def test_photo_nearly_identical_to_same_floor_earlier_is_flagged(db, monkeypatch):
    yesterday, today = await _task(db, day=TUE - timedelta(days=1)), await _task(db)
    db.add_all([
        _photo(yesterday, "floor:1", dhash="00000000000000ff", at=NOON - timedelta(days=1)),
        _photo(today, "floor:1", dhash="00000000000000fe"),                      # отличается одним битом
        _photo(today, "floor:2", dhash="ffff0000ffff0000", at=NOON + timedelta(minutes=10)),
    ])
    await db.flush()
    assert await _reasons(db, today, monkeypatch) == ("similar_photo",)


async def test_same_hash_on_another_floor_is_not_a_reason(db, monkeypatch):
    yesterday, today = await _task(db, day=TUE - timedelta(days=1)), await _task(db)
    db.add_all([
        _photo(yesterday, "floor:2", dhash="00000000000000ff", at=NOON - timedelta(days=1)),
        _photo(today, "floor:1", dhash="00000000000000ff"),
        _photo(today, "floor:2", dhash="ffff0000ffff0000", at=NOON + timedelta(minutes=10)),
    ])
    await db.flush()
    assert await _reasons(db, today, monkeypatch) == ()


async def test_all_floors_shot_within_seconds_is_too_fast(db, monkeypatch):
    today = await _task(db)
    db.add_all([_photo(today, "floor:1", dhash="00000000000000ff"),
                _photo(today, "floor:2", dhash="ffff0000ffff0000", at=NOON + timedelta(seconds=5))])
    await db.flush()
    assert await _reasons(db, today, monkeypatch) == ("too_fast",)


async def test_three_points_of_the_first_floor_count_as_one_place(db, monkeypatch):
    """Только первый этаж: три точки за полминуты — честная уборка, не «слишком быстро»."""
    today = await _task(db)
    db.add_all([
        _photo(today, "point:entry1", dhash="00000000000000ff"),
        _photo(today, "point:entry2", dhash="ffff0000ffff0000", at=NOON + timedelta(seconds=10)),
        _photo(today, "point:lift_hall", dhash="0f0f0f0f0f0f0f0f", at=NOON + timedelta(seconds=20)),
    ])
    await db.flush()
    assert await _reasons(db, today, monkeypatch) == ()
    # а первый этаж и второй за те же секунды — по-прежнему подозрительно
    db.add(_photo(today, "floor:2", dhash="f0f0f0f0f0f0f0f0", at=NOON + timedelta(seconds=12)))
    await db.flush()
    assert await _reasons(db, today, monkeypatch) == ("too_fast",)
