"""Жалоба (атомарный перевод на проверку), чистка операций и серверный выключатель."""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.cleaning import (
    CleaningComplaint,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
    CleaningTaskEvent,
)
from uk_management_bot.services.cleaning import cleanup, complaints, days
from uk_management_bot.utils.business_time import business_wall_clock

TUE = date(2026, 11, 17)
NOON = business_wall_clock(TUE, 12)
RESIDENT, CLEANER = 21, 11


@pytest.fixture
async def factory(el_async_factory, el_seed):
    async with el_async_factory() as db:
        db.add_all([
            el_seed.yard(), el_seed.building(1, entrance_count=1), el_seed.user(RESIDENT), el_seed.user(CLEANER),
            CleaningPlanVersion(building_id=1, valid_from=date(2026, 11, 1), extra_points=[], floor_count=9,
                                entrance_count=1, items=[{"work_kind": "wet", "weekdays": [1]}]),
        ])
        await db.flush()
        await days.ensure_tasks(db, TUE, now=NOON)
        await db.commit()
    return el_async_factory


async def _set_status(factory, status: str) -> int:
    async with factory() as db:
        task = (await db.execute(select(CleaningTask))).scalar_one()
        task.status = status
        await db.commit()
        return task.id


async def _complain(factory, author=RESIDENT, day=TUE):
    async with factory() as db:
        complaint = await complaints.file_complaint(db, author_id=author, building_id=1, entrance=1, work_date=day)
        await db.commit()
        return complaint.id


async def _state(factory):
    async with factory() as db:
        task = (await db.execute(select(CleaningTask))).scalar_one()
        events = (await db.execute(select(CleaningTaskEvent.kind).order_by(CleaningTaskEvent.id))).scalars().all()
        rows = (await db.execute(select(CleaningComplaint))).scalars().all()
        return task.status, events, rows


async def test_complaint_moves_accepted_task_to_review_without_any_request(factory):
    task_id = await _set_status(factory, "accepted")
    await _complain(factory)
    status, events, rows = await _state(factory)
    assert status == "review" and events == ["complaint"]
    assert (rows[0].task_id, rows[0].request_number, rows[0].outcome) == (task_id, None, "pending")


async def test_repeated_complaint_is_idempotent(factory):
    await _set_status(factory, "accepted")
    first = await _complain(factory)
    second = await _complain(factory)
    status, events, rows = await _state(factory)
    assert first == second and len(rows) == 1 and events == ["complaint"] and status == "review"


async def test_complaint_on_unfinished_task_is_recorded_but_status_stays(factory):
    await _complain(factory)
    status, events, rows = await _state(factory)
    assert status == "planned" and events == ["complaint_recorded"] and len(rows) == 1


async def test_complaint_for_day_without_task_is_kept(factory):
    await _complain(factory, day=TUE + timedelta(days=5))
    _, events, rows = await _state(factory)
    assert rows[0].task_id is None and rows[0].work_date == TUE + timedelta(days=5) and events == []


async def test_request_is_attached_later_and_pending_list_shrinks(factory):
    complaint_id = await _complain(factory)
    async with factory() as db:
        assert [c.id for c in await complaints.without_request(db)] == [complaint_id]
        await complaints.attach_request(db, complaint_id, "261117-004")
        await db.commit()
    async with factory() as db:
        assert await complaints.without_request(db) == []


# ── чистка ──────────────────────────────────────────────────────────────────

def _photo(task_id, **fields):
    base = dict(task_id=task_id, slot="floor:1", op_key=str(uuid.uuid4()), uploaded_by=CLEANER,
                upload_sha256="0" * 64, received_at=NOON, state="done")
    return CleaningPhoto(**{**base, **fields})


async def test_cleanup_abandons_stale_pending_and_drops_old_superseded_files(factory):
    task_id = await _set_status(factory, "in_progress")
    old = NOON - timedelta(days=8)
    async with factory() as db:
        db.add_all([
            _photo(task_id, state="pending", claim_token="t", claimed_at=NOON - timedelta(hours=2),
                   received_at=NOON - timedelta(hours=25)),                                            # зависла
            _photo(task_id, state="pending", claim_token="t", claimed_at=NOON - timedelta(minutes=1)), # в работе
            _photo(task_id, outcome="superseded", media_id=501, received_at=old),                     # старая замена
            _photo(task_id, outcome="activated", is_current=False, media_id=502, received_at=old),    # заменённая
            _photo(task_id, outcome="superseded", media_id=503),                                      # свежая замена
            _photo(task_id, outcome="activated", is_current=True, media_id=504, received_at=old),     # текущая
            _photo(task_id, slot="floor:2", outcome="evidence", media_id=505, received_at=old),       # доказательство
        ])
        await db.commit()
    deleted = []

    async def delete(media_id):
        deleted.append(media_id)

    stats = await cleanup.run(factory, now=NOON, media_delete=delete)

    assert sorted(deleted) == [501, 502] and stats == {"abandoned": 1, "files_dropped": 2}
    async with factory() as db:
        rows = (await db.execute(select(CleaningPhoto).order_by(CleaningPhoto.id))).scalars().all()
    assert [(r.state, r.outcome, r.refusal_code) for r in rows[:2]] == [
        ("done", "refused", "abandoned"), ("pending", None, None)]
    assert [r.media_id for r in rows[2:]] == [None, None, 503, 504, 505]


# ── серверный выключатель ───────────────────────────────────────────────────

def _job_ids(enabled: bool) -> set[str]:
    from uk_management_bot.config.settings import settings
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler

    with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler"), \
            patch.object(settings, "CLEANING_ENABLED", enabled):
        sched = ShiftScheduler()
        sched.setup_jobs()
    return {call.kwargs.get("id") for call in sched.scheduler.add_job.call_args_list}


def test_flag_is_off_by_default_and_tick_is_not_registered():
    from uk_management_bot.config.settings import Settings

    assert Settings().CLEANING_ENABLED is False
    assert "cleaning_tick" not in _job_ids(False)


def test_tick_is_registered_when_module_enabled():
    assert "cleaning_tick" in _job_ids(True)


async def test_resident_cannot_send_whole_building_to_review(factory):
    """Предел жалоб на жителя в день: повтор своей — можно, новая сверх предела — отказ."""
    async with factory() as db:
        for entrance in range(1, complaints.DAILY_LIMIT + 1):
            await complaints.file_complaint(db, author_id=RESIDENT, building_id=1, entrance=entrance, work_date=TUE)
        again = await complaints.file_complaint(db, author_id=RESIDENT, building_id=1, entrance=1, work_date=TUE)
        assert again.entrance == 1
        with pytest.raises(complaints.ComplaintLimit):
            await complaints.file_complaint(db, author_id=RESIDENT, building_id=1, entrance=9, work_date=TUE)
        other = await complaints.file_complaint(db, author_id=CLEANER, building_id=1, entrance=9, work_date=TUE)
        assert other.id is not None  # предел — на жителя, не на дом


async def test_cleanup_keeps_pending_released_after_media_outage(factory):
    """Аренда сброшена временным сбоем медиа (эпоха), телефон ещё повторяет — кадр не теряем."""
    from datetime import datetime, timezone
    task_id = await _set_status(factory, "in_progress")
    async with factory() as db:
        db.add(_photo(task_id, state="pending", claim_token="t", claimed_at=datetime(1970, 1, 1, tzinfo=timezone.utc)))
        await db.commit()

    async def delete(media_id):
        raise AssertionError

    assert (await cleanup.run(factory, now=NOON + timedelta(minutes=20), media_delete=delete))["abandoned"] == 0


async def test_complaint_on_task_under_review_bumps_version(factory):
    """Менеджер с открытой карточкой не засчитает задание, не увидев новой жалобы."""
    await _set_status(factory, "review")
    async with factory() as db:
        before = (await db.execute(select(CleaningTask))).scalar_one().version
    await _complain(factory)
    async with factory() as db:
        task = (await db.execute(select(CleaningTask))).scalar_one()
    assert task.status == "review" and task.version == before + 1
