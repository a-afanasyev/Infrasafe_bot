"""POST /api/v2/requests/{number}/before-photo — фото «до работ» исполнителя.

Статус заявки не меняется; фото — в media-service категорией `before_photo`.
Мокается только I/O: media-клиент (in-memory: загрузка + список) и Redis.
Права (назначенный исполнитель) — настоящий канон доступа на aiosqlite.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

import uk_management_bot.api.requests.executor_actions as actions
import uk_management_bot.services.executor_before_photo as before
import uk_management_bot.services.executor_completion as completion
import uk_management_bot.utils.constants as C
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.services import completion_idempotency as idem

NUMBER = "260925-001"
URL = f"/api/v2/requests/{NUMBER}/before-photo"
KEYS = [
    "6f9619ff-8b86-d011-b42d-00c04fc964ff",
    "0b8f4c1e-2f5d-4b7a-9d2e-3c4b5a697881",
    "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
    "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f60",
    "3e4f5a6b-7c8d-4e9f-a0b1-c2d3e4f5a607",
]
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 256


class FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def eval(self, script, numkeys, key, token):
        if self.data.get(key) == token:
            del self.data[key]
            return 1
        return 0


class BrokenRedis:
    async def _boom(self, *a, **k):
        raise ConnectionError("redis down")

    get = set = eval = _boom


def _executor(uid: int) -> User:
    return User(id=uid, telegram_id=70000 + uid, first_name=f"Exec{uid}",
                roles='["executor"]', active_role="executor",
                status="approved", language="ru", specialization="plumber")


def _on_shift(uid: int) -> Shift:
    return Shift(user_id=uid, status="active",
                 start_time=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))


class FakeMedia:
    """upload_report_media кладёт фото в список, get_request_media его отдаёт."""

    def __init__(self):
        self.items: list[dict] = []
        self.upload_report_media = AsyncMock(side_effect=self._upload)

    async def _upload(self, *, request_number, report_type, **_kw):
        media_id = 600 + len(self.items)
        self.items.append({"id": media_id, "category": report_type, "status": "active",
                           "file_type": "photo", "request_number": request_number})
        return {"media_file": {"id": media_id}}

    async def get_request_media(self, request_number, category=None, limit=50, retries=None):
        return [i for i in self.items
                if i["request_number"] == request_number and (category is None or i["category"] == category)]


@pytest_asyncio.fixture
async def world(db_session, manager_user, monkeypatch):
    """«Закуп» у исполнителя 41; 42 — чужой исполнитель."""
    db_session.add_all([
        _executor(41), _executor(42), _on_shift(41),
        Request(request_number=NUMBER, user_id=manager_user.id,
                category="plumbing", description="течёт кран",
                status=C.REQUEST_STATUS_PURCHASE, urgency="low",
                executor_id=41, assignment_type="individual"),
        RequestAssignment(request_number=NUMBER, assignment_type="individual",
                          executor_id=41, created_by=manager_user.id, status="active"),
    ])
    await db_session.commit()

    redis = FakeRedis()

    async def get_redis():
        return redis
    monkeypatch.setattr(idem, "get_redis", get_redis)

    media = FakeMedia()
    monkeypatch.setattr(before, "get_media_client", lambda: media)
    monkeypatch.setattr(completion, "get_media_client", lambda: media)
    return {"media": media, "redis": redis}


@pytest.fixture
def act_as(client, db_session_factory, world, monkeypatch):
    monkeypatch.setattr(actions, "AsyncSessionLocal", db_session_factory)

    async def _switch(uid: int):
        async with db_session_factory() as s:
            user = await s.get(User, uid)
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    return _switch


async def _status(factory):
    async with factory() as s:
        return (await s.get(Request, NUMBER)).status


async def _set_status(factory, status):
    async with factory() as s:
        (await s.get(Request, NUMBER)).status = status
        await s.commit()


def _post(client, *, key=KEYS[0], photo=JPEG):
    return client.post(URL, files={"photo": ("before.jpg", photo, "image/jpeg")},
                       data={"idempotency_key": key})


@pytest.mark.asyncio
async def test_uploads_before_photo_without_status_change(act_as, world, db_session_factory):
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 201, r.text
    assert r.json() == {"media_id": 600, "count": 1}
    kw = world["media"].upload_report_media.await_args.kwargs
    assert kw["report_type"] == "before_photo"
    assert kw["uploaded_by"] == 41
    assert kw["content_type"] == "image/jpeg"
    assert kw["filename"].endswith("_before.jpg")
    assert await _status(db_session_factory) == C.REQUEST_STATUS_PURCHASE


@pytest.mark.asyncio
async def test_repeat_with_same_key_does_not_upload_again(act_as, world):
    client = await act_as(41)
    assert (await _post(client)).status_code == 201
    r = await _post(client)
    assert r.status_code == 201, r.text
    assert r.json() == {"media_id": 600, "count": 1}
    world["media"].upload_report_media.assert_awaited_once()


@pytest.mark.asyncio
async def test_limit_of_four(act_as, world):
    client = await act_as(41)
    for key in KEYS[:4]:
        assert (await _post(client, key=key)).status_code == 201
    r = await _post(client, key=KEYS[4])
    assert r.status_code == 409 and r.json()["detail"] == "before_limit"
    assert world["media"].upload_report_media.await_count == 4


@pytest.mark.asyncio
async def test_replay_of_fourth_photo_after_lost_response_is_not_limit(act_as, world):
    """Ответ на 4-е фото потерялся → повтор с тем же ключом = прежний 201."""
    client = await act_as(41)
    for key in KEYS[:4]:
        assert (await _post(client, key=key)).status_code == 201
    r = await _post(client, key=KEYS[3])
    assert r.status_code == 201, r.text
    assert r.json() == {"media_id": 603, "count": 4}
    assert world["media"].upload_report_media.await_count == 4


@pytest.mark.asyncio
async def test_same_key_for_before_and_complete_are_independent(act_as, world, db_session_factory, monkeypatch):
    """Один UUID у «Фото до» и «Готово»: заявка всё равно закрывается."""
    async def noop(*_a, **_k):
        return None
    monkeypatch.setattr(actions, "publish_request_event", noop)
    monkeypatch.setattr(actions, "dispatch_notify_intents_detached", AsyncMock(return_value=0))
    await _set_status(db_session_factory, C.REQUEST_STATUS_IN_PROGRESS)
    client = await act_as(41)
    assert (await _post(client)).status_code == 201
    r = await client.post(f"/api/v2/requests/{NUMBER}/complete",
                          files={"photo": ("after.jpg", JPEG, "image/jpeg")},
                          data={"idempotency_key": KEYS[0]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == C.REQUEST_STATUS_EXECUTED
    assert [i["category"] for i in world["media"].items] == ["before_photo", "completion_photo"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [
    C.REQUEST_STATUS_IN_PROGRESS, C.REQUEST_STATUS_CLARIFICATION, C.REQUEST_STATUS_RETURNED,
])
async def test_any_open_status_is_allowed(act_as, world, db_session_factory, status):
    await _set_status(db_session_factory, status)
    client = await act_as(41)
    assert (await _post(client)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [
    C.REQUEST_STATUS_EXECUTED, C.REQUEST_STATUS_COMPLETED,
    C.REQUEST_STATUS_APPROVED, C.REQUEST_STATUS_CANCELLED,
])
async def test_closed_request_is_409_without_upload(act_as, world, db_session_factory, status):
    await _set_status(db_session_factory, status)
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 409 and r.json()["detail"] == "invalid_status"
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_not_my_request_is_403(act_as, world):
    client = await act_as(42)
    r = await _post(client)
    assert r.status_code == 403 and r.json()["detail"] == "not_assigned"
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_requires_executor_action(act_as, manager_user, world):
    client = await act_as(manager_user.id)
    assert (await _post(client)).status_code == 403
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_request_is_404(act_as, world):
    client = await act_as(41)
    r = await client.post("/api/v2/requests/260925-999/before-photo",
                          files={"photo": ("a.jpg", JPEG, "image/jpeg")},
                          data={"idempotency_key": KEYS[0]})
    assert r.status_code == 404
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_down_is_503_without_upload(act_as, world, monkeypatch):
    """Fail-closed: без хранилища повтор мог бы дать публичный дубль."""
    async def broken():
        return BrokenRedis()
    monkeypatch.setattr(idem, "get_redis", broken)
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 503 and r.json()["detail"] == "idempotency_unavailable"
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_failure_is_503(act_as, world):
    world["media"].upload_report_media.side_effect = httpx.ConnectTimeout("boom")
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 503 and r.json()["detail"] == "media_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("photo, code", [
    (b"", 422),
    (b"<html>not an image</html>", 415),
    (JPEG + b"0" * completion.COMPLETION_PHOTO_MAX_BYTES, 413),
])
async def test_bad_photo_is_rejected(act_as, world, photo, code):
    client = await act_as(41)
    assert (await _post(client, photo=photo)).status_code == code
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_idempotency_key_is_422(act_as, world):
    client = await act_as(41)
    assert (await _post(client, key="nope")).status_code == 422
