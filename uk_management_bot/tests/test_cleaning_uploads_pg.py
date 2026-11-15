"""Конкуренция загрузок фото уборки — только реальный PostgreSQL.

sqlite-тесты (tests/services/test_cleaning_uploads.py) проверяют семантику, но
блокировки строк и частичный уникальный индекс под гонкой там не работают.
Здесь параллельные запросы идут разными соединениями к DATABASE_URL бота.

Данные — в далёком будущем (2099) с id из диапазона 99xxxx; teardown удаляет всё.
Таблиц модуля нет (миграция 034 не применена) — тест пропускается.
"""
import asyncio
import io
import os
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningDay,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
    CleaningTaskEvent,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.cleaning import days, uploads
from uk_management_bot.services.cleaning.uploads import UploadRefused
from uk_management_bot.utils.business_time import business_wall_clock

DAY = date(2099, 1, 6)
NOON = business_wall_clock(DAY, 12)
YARD = BUILDING = 990001
CLEANER = 990011


def _async_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("postgres-only concurrency test (DATABASE_URL not postgres)")
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _jpeg(shade: int) -> bytes:
    img = Image.new("RGB", (64, 48))
    img.putdata([((x * 4 + shade) % 256, (y * 5) % 256, shade % 256) for y in range(48) for x in range(64)])
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


class _Media:
    def __init__(self):
        self.count, self.deleted = 0, []

    async def upload(self, task_id, user_id, jpeg, slot):
        await asyncio.sleep(0.01)  # дать гонке развернуться
        self.count += 1
        return 990000 + self.count

    async def delete(self, media_id):
        self.deleted.append(media_id)


async def _wipe(factory) -> None:
    async with factory() as db:
        task_ids = select(CleaningTask.id).where(CleaningTask.building_id == BUILDING)
        await db.execute(delete(CleaningTaskEvent).where(CleaningTaskEvent.task_id.in_(task_ids)))
        await db.execute(delete(CleaningPhoto).where(CleaningPhoto.task_id.in_(task_ids)))
        await db.execute(delete(CleaningTask).where(CleaningTask.building_id == BUILDING))
        await db.execute(delete(CleaningDay).where(CleaningDay.work_date == DAY))
        await db.execute(delete(CleaningAssignment).where(CleaningAssignment.building_id == BUILDING))
        await db.execute(delete(CleaningPlanVersion).where(CleaningPlanVersion.building_id == BUILDING))
        await db.execute(delete(Building).where(Building.id == BUILDING))
        await db.execute(delete(Yard).where(Yard.id == YARD))
        await db.execute(delete(User).where(User.id == CLEANER))
        await db.commit()


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine(_async_url(), pool_size=12, max_overflow=4)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        if (await db.execute(text("SELECT to_regclass('cleaning_photos')"))).scalar() is None:
            await engine.dispose()
            pytest.skip("таблиц модуля «Уборка» нет — миграция 034 не применена")
    await _wipe(factory)
    async with factory() as db:
        db.add_all([
            Yard(id=YARD, name=f"cleaning-pg-{YARD}", is_active=True),
            User(id=CLEANER, telegram_id=9_900_000_011, first_name="PG", roles='["executor"]',
                 active_role="executor", status="approved", language="ru"),
        ])
        await db.flush()
        db.add(Building(id=BUILDING, yard_id=YARD, address="cleaning-pg", entrance_count=1,
                        floor_count=9, is_active=True))
        await db.flush()
        db.add_all([
            CleaningPlanVersion(building_id=BUILDING, valid_from=date(2098, 12, 1), extra_points=[],
                                floor_count=9, entrance_count=1,
                                items=[{"work_kind": "wet", "weekdays": list(range(7)),
                                        "floor_from": 1, "floor_to": 2}]),
            CleaningAssignment(building_id=BUILDING, entrance=1, user_id=CLEANER, valid_from=date(2098, 12, 1)),
        ])
        await db.flush()
        await days.ensure_tasks(db, DAY, now=NOON)
        task_id = (await db.execute(
            select(CleaningTask.id).where(CleaningTask.building_id == BUILDING))).scalar_one()
        await db.commit()
    media = _Media()
    try:
        yield factory, media, task_id
    finally:
        await _wipe(factory)
        await engine.dispose()


async def _send(env, *, slot="floor:1", key=None, shade=0, captured=None):
    factory, media, task_id = env
    try:
        return await uploads.upload_photo(
            factory, user_id=CLEANER, task_id=task_id, slot=slot, op_key=key or str(uuid.uuid4()),
            photo_bytes=_jpeg(shade), client_captured_at=captured or NOON, now=NOON,
            media_upload=media.upload, media_delete=media.delete)
    except UploadRefused as exc:
        return exc


async def _rows(env, *criteria):
    factory, _, task_id = env
    async with factory() as db:
        return list((await db.execute(
            select(CleaningPhoto).where(CleaningPhoto.task_id == task_id, *criteria))).scalars())


async def test_same_key_sent_in_parallel_creates_one_operation(env):
    key = str(uuid.uuid4())
    results = await asyncio.gather(*[_send(env, key=key, shade=5) for _ in range(8)])

    rows = await _rows(env)
    assert len(rows) == 1 and rows[0].state == "done" and rows[0].is_current
    done = [r for r in results if not isinstance(r, UploadRefused)]
    assert done and {r.media_id for r in done} == {rows[0].media_id}
    assert {r.code for r in results if isinstance(r, UploadRefused)} <= {"in_progress"}
    # лишние файлы проигравших удалены: в медиа-сервисе остался ровно один
    assert env[1].count - len(env[1].deleted) == 1


async def test_parallel_retakes_leave_exactly_one_current_and_it_is_the_newest(env):
    shots = [(i, NOON + timedelta(seconds=i)) for i in range(1, 9)]
    results = await asyncio.gather(*[_send(env, shade=i * 20, captured=at) for i, at in shots])

    assert not [r for r in results if isinstance(r, UploadRefused)]
    assert {r.outcome for r in results} <= {"activated", "superseded"}
    current = await _rows(env, CleaningPhoto.is_current.is_(True))
    assert len(current) == 1
    assert current[0].client_captured_at == shots[-1][1]


async def test_last_slots_finished_in_parallel_complete_the_task_once(env):
    factory, _, task_id = env
    await asyncio.gather(_send(env, slot="floor:1", shade=10), _send(env, slot="floor:2", shade=130))
    async with factory() as db:
        task = await db.get(CleaningTask, task_id)
        completed = (await db.execute(
            select(func.count()).select_from(CleaningTaskEvent)
            .where(CleaningTaskEvent.task_id == task_id, CleaningTaskEvent.kind == "completed"))).scalar_one()
    assert task.status == "review" and completed == 1  # фото без сессии → на проверку, ровно один раз


async def test_partial_unique_index_forbids_two_current_photos_of_a_slot(env):
    factory, _, task_id = env

    def _photo():
        return CleaningPhoto(task_id=task_id, slot="floor:1", op_key=str(uuid.uuid4()), uploaded_by=CLEANER,
                             upload_sha256="0" * 64, state="done", is_current=True, received_at=NOON)

    async with factory() as db:
        db.add(_photo())
        await db.commit()
    with pytest.raises(IntegrityError):
        async with factory() as db:
            db.add(_photo())
            await db.commit()


async def test_generation_run_in_parallel_creates_tasks_once(env):
    factory, _, _ = env
    other = DAY + timedelta(days=1)

    async def generate():
        async with factory() as db:
            await days.ensure_tasks(db, other, now=business_wall_clock(other, 12))
            await db.commit()

    try:
        await asyncio.gather(*[generate() for _ in range(6)])
        async with factory() as db:
            count = (await db.execute(
                select(func.count()).select_from(CleaningTask)
                .where(CleaningTask.building_id == BUILDING, CleaningTask.work_date == other))).scalar_one()
        assert count == 1
    finally:
        async with factory() as db:
            await db.execute(delete(CleaningTask).where(CleaningTask.work_date == other))
            await db.execute(delete(CleaningDay).where(CleaningDay.work_date == other))
            await db.commit()
