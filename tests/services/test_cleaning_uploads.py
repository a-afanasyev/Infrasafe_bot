"""Протокол загрузки фото уборки: повтор, аренда, финализация, пересъёмка, поздние фото.

Семантика на sqlite; чередования задаёт подменный загрузчик в медиа-сервис —
он исполняется между приёмом (фаза А) и финализацией (фаза В). Настоящая
конкуренция соединений — в uk_management_bot/tests/test_cleaning_uploads_pg.py.
"""
import io
import uuid
from datetime import date, timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningComplaint,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
)
from uk_management_bot.services.cleaning import days, uploads
from uk_management_bot.services.cleaning.uploads import UploadRefused
from uk_management_bot.utils.business_time import business_wall_clock

TUE = date(2026, 11, 17)
NOON = business_wall_clock(TUE, 12)
END = business_wall_clock(TUE, 23, 59)
CLEANER, OTHER = 11, 12


def _jpeg(shade: int = 0) -> bytes:
    """Разные ``shade`` дают заведомо разные кадры (градиент + сдвиг)."""
    img = Image.new("RGB", (64, 48))
    img.putdata([((x * 4 + shade) % 256, (y * 5) % 256, shade % 256) for y in range(48) for x in range(64)])
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def _no_sampling_no_probation(monkeypatch):
    async def not_on_probation(*args, **kwargs):
        return False

    monkeypatch.setattr(uploads.acceptance, "pick_sampled", lambda rules: False)
    monkeypatch.setattr(uploads.acceptance, "on_probation", not_on_probation)


class FakeMedia:
    """Подмена медиа-сервиса: выдаёт id, помнит удаления, умеет вклиниваться."""

    def __init__(self):
        self.next_id, self.deleted, self.hook, self.fail = 100, [], None, None

    async def upload(self, task_id, user_id, jpeg, slot):
        if self.hook is not None:
            hook, self.hook = self.hook, None
            await hook()
        if self.fail is not None:
            code, self.fail = self.fail, None
            raise uploads.MediaFailure(code)
        self.next_id += 1
        return self.next_id

    async def delete(self, media_id):
        self.deleted.append(media_id)


@pytest.fixture
async def env(el_async_factory, el_seed):
    """Вторник, дом 1 с одним подъездом, слоты floor:1 и floor:2, ответственный CLEANER."""
    async with el_async_factory() as db:
        db.add_all([
            el_seed.yard(), el_seed.building(1, entrance_count=1), el_seed.user(CLEANER), el_seed.user(OTHER),
            CleaningPlanVersion(building_id=1, valid_from=date(2026, 11, 1), extra_points=[], floor_count=9,
                                entrance_count=1,
                                items=[{"work_kind": "wet", "weekdays": [1], "floor_from": 1, "floor_to": 2}]),
            CleaningAssignment(building_id=1, entrance=1, user_id=CLEANER, valid_from=date(2026, 11, 1)),
        ])
        await db.flush()
        await days.ensure_tasks(db, TUE, now=NOON)
        task_id = (await db.execute(select(CleaningTask.id))).scalar_one()
        await db.commit()
    return el_async_factory, FakeMedia(), task_id


async def _send(env, *, slot="floor:1", key=None, shade=0, now=NOON, user=CLEANER, captured=None, data=None):
    factory, media, task_id = env
    return await uploads.upload_photo(
        factory, user_id=user, task_id=task_id, slot=slot, op_key=key or str(uuid.uuid4()),
        photo_bytes=data if data is not None else _jpeg(shade), client_captured_at=captured or now,
        now=now, media_upload=media.upload, media_delete=media.delete,
    )


async def _task(env) -> CleaningTask:
    factory, _, task_id = env
    async with factory() as db:
        return await db.get(CleaningTask, task_id)


async def _open(env, now=NOON):
    factory, _, task_id = env
    async with factory() as db:
        await uploads.open_session(db, task_id, CLEANER, now=now)
        await db.commit()


async def _photos(env) -> list[CleaningPhoto]:
    factory, _, _ = env
    async with factory() as db:
        return list((await db.execute(select(CleaningPhoto).order_by(CleaningPhoto.id))).scalars())


# ── обычный путь ────────────────────────────────────────────────────────────

async def test_first_photo_activates_and_starts_the_task(env):
    result = await _send(env)
    assert (result.outcome, result.replay) == ("activated", False)
    assert (await _task(env)).status == "in_progress"
    photo = (await _photos(env))[0]
    assert photo.is_current and photo.state == "done" and photo.trust_level == "offline"
    assert photo.pixel_sha256 and len(photo.dhash) == 16


async def test_last_slot_with_live_photos_is_accepted_automatically(env, monkeypatch):
    _no_sampling_no_probation(monkeypatch)
    await _open(env)
    await _send(env, slot="floor:1", shade=1)
    await _send(env, slot="floor:2", shade=90, now=NOON + timedelta(minutes=20))
    task = await _task(env)
    assert task.status == "accepted" and task.sampled is False


async def test_offline_photos_send_completed_task_to_review(env):
    await _send(env, slot="floor:1", shade=1)
    await _send(env, slot="floor:2", shade=90)
    assert (await _task(env)).status == "review"


async def test_system_camera_photo_never_gets_live_trust(env):
    factory, media, task_id = env
    await _open(env)
    await uploads.upload_photo(
        factory, user_id=CLEANER, task_id=task_id, slot="floor:1", op_key=str(uuid.uuid4()),
        photo_bytes=_jpeg(1), now=NOON, system_camera=True, media_upload=media.upload, media_delete=media.delete)
    assert [p.trust_level for p in await _photos(env)] == ["offline"]


async def test_trust_levels_follow_session_window(env):
    await _open(env)
    await _open(env, now=NOON + timedelta(hours=1))  # повторное открытие окно не продлевает
    await _send(env, slot="floor:1", shade=1, now=NOON + timedelta(minutes=119))
    await _send(env, slot="floor:2", shade=90, now=NOON + timedelta(minutes=121))
    assert [p.trust_level for p in await _photos(env)] == ["live", "deferred"]


# ── повтор и ключ ───────────────────────────────────────────────────────────

async def test_replay_returns_saved_outcome_even_after_day_end_and_freeze(env):
    key = str(uuid.uuid4())
    first = await _send(env, key=key, shade=1)
    await _send(env, slot="floor:2", shade=90)  # задание завершено → заморожено
    again = await _send(env, key=key, shade=1, now=END + timedelta(hours=30))
    assert (again.outcome, again.replay, again.media_id) == ("activated", True, first.media_id)
    assert len(await _photos(env)) == 2


@pytest.mark.parametrize("change", [{"shade": 7}, {"slot": "floor:2"}])
async def test_same_key_with_other_content_or_slot_is_rejected(env, change):
    key = str(uuid.uuid4())
    await _send(env, key=key, shade=1)
    with pytest.raises(UploadRefused) as exc:
        await _send(env, key=key, **{"shade": 1, **change})
    assert (exc.value.code, exc.value.http_status) == ("key_reused", 409)


async def test_foreign_user_cannot_probe_someone_elses_key(env):
    key = str(uuid.uuid4())
    await _send(env, key=key, shade=1)
    with pytest.raises(UploadRefused) as exc:
        await _send(env, key=key, shade=1, user=OTHER)
    assert exc.value.http_status == 404


async def test_refusal_is_saved_and_replayed_with_the_same_code(env):
    key = str(uuid.uuid4())
    first = await _send(env, key=key, slot="floor:7")  # этажа нет в задании
    again = await _send(env, key=key, slot="floor:7")
    assert (first.outcome, first.refusal_code) == ("refused", "bad_slot")
    assert (again.outcome, again.refusal_code, again.replay) == ("refused", "bad_slot", True)
    assert (await _send(env, user=OTHER)).refusal_code == "not_yours"


async def test_broken_image_is_rejected_before_any_row(env):
    with pytest.raises(UploadRefused) as exc:
        await _send(env, data=b"\xff\xd8\xff\xe0" + b"not a jpeg" * 20)
    assert exc.value.http_status in (415, 422)
    assert await _photos(env) == []


# ── аренда ──────────────────────────────────────────────────────────────────

async def test_retry_while_winner_still_uploads_gets_in_progress(env):
    key = str(uuid.uuid4())
    seen = {}

    async def retry_meanwhile():
        with pytest.raises(UploadRefused) as exc:
            await _send(env, key=key, shade=1)
        seen["code"] = (exc.value.code, exc.value.http_status)

    env[1].hook = retry_meanwhile
    result = await _send(env, key=key, shade=1)
    assert seen["code"] == ("in_progress", 409)
    assert result.outcome == "activated" and len(await _photos(env)) == 1


async def test_stale_lease_is_taken_over_and_loser_deletes_its_file(env):
    key = str(uuid.uuid4())
    seen = {}

    async def takeover_later():  # первый обработчик «завис»: аренда истекла, пришёл повтор
        seen["winner"] = await _send(env, key=key, shade=1, now=NOON + timedelta(minutes=3))

    env[1].hook = takeover_later
    loser = await _send(env, key=key, shade=1)
    assert seen["winner"].outcome == "activated"
    assert (loser.outcome, loser.replay, loser.media_id) == ("activated", True, seen["winner"].media_id)
    assert env[1].deleted == [seen["winner"].media_id + 1]  # файл проигравшего удалён
    assert len(await _photos(env)) == 1


async def test_temporary_media_failure_leaves_operation_retryable(env):
    key = str(uuid.uuid4())
    env[1].fail = "media_unavailable"
    with pytest.raises(UploadRefused) as exc:
        await _send(env, key=key, shade=1)
    assert exc.value.http_status == 503
    result = await _send(env, key=key, shade=1, now=NOON + timedelta(minutes=3))
    assert result.outcome == "activated"


async def test_permanent_media_rejection_is_a_saved_refusal(env):
    env[1].fail = "media_rejected"
    result = await _send(env)
    assert (result.outcome, result.refusal_code) == ("refused", "bad_photo")


# ── финализация после изменений ─────────────────────────────────────────────

async def test_finalization_after_responsible_changed_keeps_photo_as_evidence(env):
    factory, media, task_id = env

    async def reassign():
        async with factory() as db:
            (await db.get(CleaningTask, task_id)).responsible_id = OTHER
            await db.commit()

    media.hook = reassign
    result = await _send(env)
    photo = (await _photos(env))[0]
    assert result.outcome == "evidence" and photo.is_current is False
    assert (await _task(env)).status == "planned"


async def test_on_time_photo_finalized_after_day_closed_is_evidence(env):
    factory, media, _ = env

    async def close():
        async with factory() as db:
            await days.close_days(db, now=END + timedelta(minutes=6))
            await db.commit()

    media.hook = close
    result = await _send(env, now=END - timedelta(seconds=10))
    assert result.outcome == "evidence"
    assert (await _task(env)).status == "missed"


async def test_frozen_task_refuses_new_photos_and_deletes_nothing_stored(env):
    await _send(env, slot="floor:1", shade=1)
    await _send(env, slot="floor:2", shade=90)
    result = await _send(env, slot="floor:1", shade=200)
    assert (result.outcome, result.refusal_code) == ("refused", "frozen")
    assert [p.is_current for p in await _photos(env)] == [True, True, False]


# ── пересъёмка ──────────────────────────────────────────────────────────────

async def test_older_shot_finalized_later_does_not_replace_newer_one(env):
    old, new = NOON, NOON + timedelta(minutes=5)
    seen = {}

    async def newer_goes_first():
        seen["new"] = await _send(env, shade=120, captured=new, now=new)

    env[1].hook = newer_goes_first
    late_old = await _send(env, shade=1, captured=old, now=old)
    assert seen["new"].outcome == "activated" and late_old.outcome == "superseded"
    current = [p for p in await _photos(env) if p.is_current]
    assert len(current) == 1 and current[0].media_id == seen["new"].media_id


async def test_retake_replaces_current_photo(env):
    await _send(env, shade=1, captured=NOON)
    again = await _send(env, shade=120, captured=NOON + timedelta(minutes=1), now=NOON + timedelta(minutes=1))
    assert again.outcome == "activated"
    assert [p.is_current for p in await _photos(env)] == [False, True]


# ── поздние доказательства ──────────────────────────────────────────────────

async def test_photo_between_day_end_and_closing_is_saved_as_evidence(env):
    result = await _send(env, now=END + timedelta(minutes=2))  # день ещё не закрыт
    photo = (await _photos(env))[0]
    assert (result.outcome, photo.trust_level, photo.is_current) == ("evidence", "late", False)
    assert (await _task(env)).status == "planned"


async def test_late_evidence_for_missed_task_does_not_change_status(env):
    factory, _, _ = env
    async with factory() as db:
        await days.close_days(db, now=END + timedelta(minutes=6))
        await db.commit()
    result = await _send(env, now=END + timedelta(hours=3))
    assert result.outcome == "evidence" and (await _task(env)).status == "missed"


async def test_photo_later_than_late_window_is_refused(env):
    result = await _send(env, now=END + timedelta(hours=25))
    assert (result.outcome, result.refusal_code) == ("refused", "too_late")


# ── жалоба ──────────────────────────────────────────────────────────────────

async def test_complaint_on_unfinished_task_sends_it_to_review_on_completion(env, monkeypatch):
    _no_sampling_no_probation(monkeypatch)
    factory, _, task_id = env
    await _open(env)
    async with factory() as db:
        db.add(CleaningComplaint(building_id=1, entrance=1, work_date=TUE, author_id=OTHER, task_id=task_id))
        await db.commit()
    await _send(env, slot="floor:1", shade=1)
    await _send(env, slot="floor:2", shade=90)
    assert (await _task(env)).status == "review"


@pytest.mark.parametrize("code,status,expected", [
    ("media_rejected", 502, "media_rejected"),      # окончательный отказ: статус тоже 5xx
    ("media_unavailable", 503, "media_unavailable"),
])
async def test_media_failure_is_classified_by_code_not_status(monkeypatch, code, status, expected):
    from uk_management_bot.services.executor_completion import CompletionRefused

    async def refuse(*args, **kwargs):
        raise CompletionRefused(code, status)

    monkeypatch.setattr(uploads, "upload_executor_photo", refuse)
    with pytest.raises(uploads.MediaFailure) as caught:
        await uploads._media_upload(1, 1, b"x", "floor:1")
    assert caught.value.code == expected


async def test_first_floor_points_are_uploaded_and_complete_the_task(
        el_async_factory, el_seed, monkeypatch, cleaning_first_floor_points):
    """Боевые точки первого этажа проходят всю загрузку: формат имени, слот задания, завершение."""
    from uk_management_bot.services.cleaning import planning

    planning.FIRST_FLOOR_POINTS = cleaning_first_floor_points
    _no_sampling_no_probation(monkeypatch)
    async with el_async_factory() as db:
        db.add_all([
            el_seed.yard(), el_seed.building(1, entrance_count=1), el_seed.user(CLEANER),
            CleaningPlanVersion(building_id=1, valid_from=date(2026, 11, 1), extra_points=[], floor_count=2,
                                entrance_count=1, items=[{"work_kind": "wet", "weekdays": [1]}]),
            CleaningAssignment(building_id=1, entrance=1, user_id=CLEANER, valid_from=date(2026, 11, 1)),
        ])
        await db.flush()
        await days.ensure_tasks(db, TUE, now=NOON)
        task = (await db.execute(select(CleaningTask))).scalar_one()
        slots, task_id = list(task.slots_required), task.id
        await db.commit()
    assert slots == ["point:entry1", "point:entry2", "point:lift_hall", "floor:2"]

    env = (el_async_factory, FakeMedia(), task_id)
    await _open(env)
    for step, slot in enumerate(slots):
        result = await _send(env, slot=slot, shade=step * 60 + 1, now=NOON + timedelta(minutes=5 * step))
        assert result.outcome == "activated", (slot, result.refusal_code)
    assert (await _task(env)).status == "accepted"


@pytest.mark.parametrize("slot,ok", [
    ("point:entry1", True), ("point:lift_hall", True), ("floor:12", True),
    ("point:1entry", False), ("point:", False), ("floor:0", False), ("point:Entry", False),
])
def test_slot_name_format(slot, ok):
    assert (uploads.SLOT_RE.fullmatch(slot) is not None) is ok
