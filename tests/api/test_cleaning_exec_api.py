"""API уборщицы: задания на сегодня, сессия, загрузка фото этажа, просмотр своего фото."""
import io
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

import uk_management_bot.api.cleaning.router_exec as router_exec
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.cleaning import uploads
from uk_management_bot.utils.business_time import business_today

BASE = "/api/v2/cleaning"
CLEANER, OTHER = 601, 602


def _jpeg(shade: int = 0) -> bytes:
    img = Image.new("RGB", (64, 48))
    img.putdata([((x * 4 + shade) % 256, (y * 5) % 256, shade % 256) for y in range(48) for x in range(64)])
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


@pytest_asyncio.fixture
async def world(db_session, db_session_factory, monkeypatch):
    """Сегодня по плану: дом 1, подъезд 1, этажи 1–2, ответственный CLEANER."""
    monkeypatch.setattr(settings, "CLEANING_ENABLED", True)
    monkeypatch.setattr(router_exec, "AsyncSessionLocal", db_session_factory)
    stored: dict[int, bytes] = {}

    async def media_upload(task_id, user_id, jpeg, slot):
        stored[len(stored) + 1] = jpeg
        return len(stored)

    async def media_download(media_id, preview=False):
        return (stored[media_id], "image/jpeg") if media_id in stored else None

    monkeypatch.setattr(uploads, "_media_upload", media_upload)
    monkeypatch.setattr(router_exec, "_media_upload", media_upload)
    monkeypatch.setattr(router_exec, "_download", media_download)

    def staff(uid: int) -> User:
        return User(id=uid, telegram_id=9000 + uid, first_name=f"S{uid}", roles='["executor"]',
                    active_role="executor", status="approved", language="ru", specialization="cleaning")

    today = business_today()
    db_session.add(Yard(id=1, name="Двор", is_active=True))
    await db_session.flush()
    db_session.add_all([
        Building(id=1, yard_id=1, address="д. 12", entrance_count=1, floor_count=9, is_active=True),
        staff(CLEANER), staff(OTHER),
    ])
    await db_session.flush()
    db_session.add_all([
        CleaningPlanVersion(building_id=1, valid_from=today - timedelta(days=3), extra_points=[], floor_count=9,
                            entrance_count=1,
                            items=[{"work_kind": "wet", "weekdays": list(range(7)), "floor_from": 1, "floor_to": 2}]),
        CleaningAssignment(building_id=1, entrance=1, user_id=CLEANER, valid_from=today - timedelta(days=3)),
    ])
    await db_session.commit()
    return stored


@pytest.fixture
def act_as(client, db_session_factory):
    async def _as(user_id: int):
        async with db_session_factory() as db:
            user = await db.get(User, user_id)

        async def current():
            return user

        app.dependency_overrides[get_current_user] = current
        return client

    return _as


async def _upload(client, task_id, *, slot="floor:1", key=None, shade=0):
    return await client.post(
        f"{BASE}/tasks/{task_id}/photos",
        files={"photo": ("f.jpg", _jpeg(shade), "image/jpeg")},
        data={"slot": slot, "op_key": key or str(uuid.uuid4())},
    )


@pytest.mark.asyncio
async def test_today_generates_tasks_lazily_and_shows_slots(world, act_as):
    client = await act_as(CLEANER)
    body = (await client.get(f"{BASE}/my/tasks")).json()
    (task,) = body["tasks"]
    assert (task["address"], task["entrance"], task["works"], task["status"]) == ("д. 12", 1, ["wet"], "planned")
    assert [(s["slot"], s["done"]) for s in task["slots"]] == [("floor:1", False), ("floor:2", False)]
    assert body["day_end_at"] and task["session_open"] is False

    assert (await client.post(f"{BASE}/tasks/{task['id']}/session")).status_code == 204
    assert (await client.get(f"{BASE}/my/tasks")).json()["tasks"][0]["session_open"] is True
    other = await act_as(OTHER)
    assert (await other.get(f"{BASE}/my/tasks")).json()["tasks"] == []


@pytest.mark.asyncio
async def test_photo_marks_floor_and_replay_is_stable(world, act_as):
    client = await act_as(CLEANER)
    task_id = (await client.get(f"{BASE}/my/tasks")).json()["tasks"][0]["id"]
    key = str(uuid.uuid4())

    first = await _upload(client, task_id, key=key, shade=1)
    assert first.status_code == 200, first.text
    assert (first.json()["outcome"], first.json()["replay"], first.json()["task_status"]) == ("activated", False, "in_progress")
    again = await _upload(client, task_id, key=key, shade=1)
    assert (again.json()["outcome"], again.json()["replay"], again.json()["photo_id"]) == ("activated", True, first.json()["photo_id"])

    slots = (await client.get(f"{BASE}/my/tasks")).json()["tasks"][0]["slots"]
    assert [(s["slot"], s["done"]) for s in slots] == [("floor:1", True), ("floor:2", False)]
    assert slots[0]["photo_id"] == first.json()["photo_id"]

    done = await _upload(client, task_id, slot="floor:2", shade=90)
    assert done.json()["task_status"] == "review"  # фото без сессии → на проверку


@pytest.mark.asyncio
@pytest.mark.parametrize("data, status, detail", [
    ({"slot": "floor:1", "op_key": "not-a-uuid"}, 422, "invalid_idempotency_key"),
    ({"slot": "roof", "op_key": str(uuid.uuid4())}, 422, "bad_slot"),
])
async def test_bad_upload_is_rejected(world, act_as, data, status, detail):
    client = await act_as(CLEANER)
    task_id = (await client.get(f"{BASE}/my/tasks")).json()["tasks"][0]["id"]
    resp = await client.post(f"{BASE}/tasks/{task_id}/photos",
                             files={"photo": ("f.jpg", _jpeg(), "image/jpeg")}, data=data)
    assert (resp.status_code, resp.json()["detail"]) == (status, detail)


@pytest.mark.asyncio
async def test_foreign_cleaner_cannot_use_someone_elses_task(world, act_as, db_session_factory):
    """IDOR: чужое задание — сессия 404, фото получает сохранённый отказ и не активируется."""
    owner = await act_as(CLEANER)
    task_id = (await owner.get(f"{BASE}/my/tasks")).json()["tasks"][0]["id"]
    photo_id = (await _upload(owner, task_id, shade=1)).json()["photo_id"]

    stranger = await act_as(OTHER)
    assert (await stranger.post(f"{BASE}/tasks/{task_id}/session")).status_code == 404
    refused = await _upload(stranger, task_id, slot="floor:2", shade=50)
    assert (refused.status_code, refused.json()["outcome"], refused.json()["refusal_code"]) == (200, "refused", "not_yours")
    assert (await stranger.get(f"{BASE}/tasks/{task_id}/photos/{photo_id}/file")).status_code == 404
    async with db_session_factory() as db:
        task = await db.get(CleaningTask, task_id)
        current = (await db.execute(select(CleaningPhoto).where(CleaningPhoto.is_current.is_(True)))).scalars().all()
    assert task.session_opened_at is None and [p.slot for p in current] == ["floor:1"]


@pytest.mark.asyncio
async def test_own_photo_file_is_served_without_cache(world, act_as):
    client = await act_as(CLEANER)
    task_id = (await client.get(f"{BASE}/my/tasks")).json()["tasks"][0]["id"]
    photo_id = (await _upload(client, task_id, shade=1)).json()["photo_id"]

    resp = await client.get(f"{BASE}/tasks/{task_id}/photos/{photo_id}/file")
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "no-store" and resp.content[:2] == b"\xff\xd8"
    assert (await client.get(f"{BASE}/tasks/{task_id + 99}/photos/{photo_id}/file")).status_code == 404
    assert (await client.get(f"{BASE}/tasks/{task_id}/photos/{photo_id + 99}/file")).status_code == 404


@pytest.mark.asyncio
async def test_disabled_module_and_wrong_role(world, act_as, client, monkeypatch):
    assert (await client.get(f"{BASE}/my/tasks")).status_code == 403  # менеджер — не уборщица
    cleaner = await act_as(CLEANER)
    monkeypatch.setattr(settings, "CLEANING_ENABLED", False)
    assert (await cleaner.get(f"{BASE}/my/tasks")).status_code == 404
    assert (await cleaner.post(f"{BASE}/tasks/1/session")).status_code == 404
    assert (await _upload(cleaner, 1)).status_code == 404
