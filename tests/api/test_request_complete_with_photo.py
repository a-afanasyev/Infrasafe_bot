"""POST /api/v2/requests/{number}/complete — атомарное «Готово» с фото «после».

Дефект, который закрывает эндпоинт: TWA сначала PATCH'ила «Выполнена», потом
грузила фото по одному без ретраев — фото терялись, заявка оставалась
закрытой без фотоотчёта. Теперь фото → media-service, и только потом переход.

Мокается только I/O: media-клиент (сеть к media-service) и Redis (in-memory).
Канон EXECUTOR_COMPLETE — настоящий, на aiosqlite.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

import uk_management_bot.api.requests.executor_actions as actions
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
URL = f"/api/v2/requests/{NUMBER}/complete"
KEY = "6f9619ff-8b86-d011-b42d-00c04fc964ff"
KEY2 = "0b8f4c1e-2f5d-4b7a-9d2e-3c4b5a697881"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 256


class FakeRedis:
    """In-memory get/set(nx, ex)/delete — всё, что трогает хранилище."""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def delete(self, key):
        return 1 if self.data.pop(key, None) is not None else 0


class BrokenRedis:
    async def _boom(self, *a, **k):
        raise ConnectionError("redis down")

    get = set = delete = _boom


def _executor(uid: int) -> User:
    return User(id=uid, telegram_id=70000 + uid, first_name=f"Exec{uid}",
                roles='["executor"]', active_role="executor",
                status="approved", language="ru", specialization="plumber")


def _on_shift(uid: int) -> Shift:
    return Shift(user_id=uid, status="active",
                 start_time=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))


def _media_ok(media_id: int = 501):
    client = MagicMock()
    client.upload_report_media = AsyncMock(return_value={
        "media_file": {"id": media_id}, "file_url": f"/api/v1/media/{media_id}/file"})
    return client


@pytest_asyncio.fixture
async def world(db_session, manager_user, monkeypatch):
    """«В работе» у исполнителя 41 (на смене); 42 — на смене, чужой; 43 — без смены."""
    db_session.add_all([
        _executor(41), _executor(42), _executor(43),
        _on_shift(41), _on_shift(42),
        Request(request_number=NUMBER, user_id=manager_user.id,
                category="plumbing", description="течёт кран",
                status=C.REQUEST_STATUS_IN_PROGRESS, urgency="low",
                executor_id=41, assignment_type="individual"),
        RequestAssignment(request_number=NUMBER, assignment_type="individual",
                          executor_id=41, created_by=manager_user.id, status="active"),
    ])
    await db_session.commit()

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(actions, "publish_request_event", noop)
    notify = AsyncMock(return_value=0)
    monkeypatch.setattr(actions, "dispatch_notify_intents_detached", notify)

    redis = FakeRedis()

    async def get_redis():
        return redis
    monkeypatch.setattr(idem, "get_redis", get_redis)

    media = _media_ok()
    monkeypatch.setattr(completion, "get_media_client", lambda: media)
    return {"media": media, "notify": notify, "redis": redis}


@pytest.fixture
def act_as(client, db_session_factory, world, monkeypatch):
    monkeypatch.setattr(actions, "AsyncSessionLocal", db_session_factory)

    async def _switch(uid: int):
        async with db_session_factory() as s:
            user = await s.get(User, uid)
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    return _switch


async def _status(factory, number=NUMBER):
    async with factory() as s:
        return (await s.get(Request, number)).status


def _post(client, *, photo=JPEG, key=KEY, name="after.jpg", ctype="image/jpeg"):
    return client.post(URL, files={"photo": (name, photo, ctype)},
                       data={"idempotency_key": key})


@pytest.mark.asyncio
async def test_complete_uploads_photo_then_closes_request(act_as, world, db_session_factory):
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request_number"] == NUMBER
    assert body["status"] == C.REQUEST_STATUS_EXECUTED
    assert await _status(db_session_factory) == C.REQUEST_STATUS_EXECUTED

    upload = world["media"].upload_report_media
    upload.assert_awaited_once()
    kw = upload.await_args.kwargs
    assert kw["request_number"] == NUMBER
    assert kw["report_type"] == "completion_photo"
    assert kw["uploaded_by"] == 41
    assert kw["content_type"] == "image/jpeg"  # server-derived, не клиентский
    assert kw["file_path"].read() == JPEG
    # notify-интенты EXECUTOR_COMPLETE (жителю «выполнено») — после ответа
    world["notify"].assert_awaited_once()


@pytest.mark.asyncio
async def test_media_failure_keeps_status(act_as, world, db_session_factory):
    world["media"].upload_report_media.side_effect = httpx.ConnectTimeout("boom")
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "media_unavailable"
    assert await _status(db_session_factory) == C.REQUEST_STATUS_IN_PROGRESS
    world["notify"].assert_not_awaited()


@pytest.mark.asyncio
async def test_media_5xx_is_503_and_4xx_is_502(act_as, world, db_session_factory):
    req = httpx.Request("POST", "http://media/api/v1/media/upload-report")
    world["media"].upload_report_media.side_effect = httpx.HTTPStatusError(
        "x", request=req, response=httpx.Response(500, request=req))
    client = await act_as(41)
    assert (await _post(client)).status_code == 503

    world["media"].upload_report_media.side_effect = httpx.HTTPStatusError(
        "x", request=req, response=httpx.Response(400, request=req))
    r = await _post(client, key=KEY2)
    assert r.status_code == 502 and r.json()["detail"] == "media_rejected"
    assert await _status(db_session_factory) == C.REQUEST_STATUS_IN_PROGRESS


@pytest.mark.asyncio
async def test_media_disabled_is_503(act_as, world, monkeypatch, db_session_factory):
    monkeypatch.setattr(completion, "get_media_client", lambda: None)
    client = await act_as(41)
    assert (await _post(client)).status_code == 503
    assert await _status(db_session_factory) == C.REQUEST_STATUS_IN_PROGRESS


@pytest.mark.asyncio
async def test_repeat_with_same_key_does_not_upload_again(act_as, world):
    client = await act_as(41)
    assert (await _post(client)).status_code == 200
    r = await _post(client)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == C.REQUEST_STATUS_EXECUTED
    world["media"].upload_report_media.assert_awaited_once()
    world["notify"].assert_awaited_once()  # повтор не шлёт уведомление второй раз


@pytest.mark.asyncio
async def test_already_completed_by_me_with_new_key_is_200_without_upload(act_as, world):
    """Естественная идемпотентность: работает и без записи в Redis."""
    client = await act_as(41)
    assert (await _post(client)).status_code == 200
    world["redis"].data.clear()
    r = await _post(client, key=KEY2)
    assert r.status_code == 200, r.text
    world["media"].upload_report_media.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_after_workflow_failure_reuses_uploaded_photo(
        act_as, world, monkeypatch, db_session_factory):
    """Фото загрузилось, переход упал → фото остаётся в заявке; повтор с тем же
    ключом не грузит его второй раз и закрывает заявку."""
    from uk_management_bot.utils.request_workflow import WorkflowError

    real = completion.run_command_async
    calls = {"n": 0}

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise WorkflowError("db blip")
        return await real(*a, **k)

    monkeypatch.setattr(completion, "run_command_async", flaky)
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 422, r.text
    assert await _status(db_session_factory) == C.REQUEST_STATUS_IN_PROGRESS

    r = await _post(client)
    assert r.status_code == 200, r.text
    assert await _status(db_session_factory) == C.REQUEST_STATUS_EXECUTED
    world["media"].upload_report_media.assert_awaited_once()


@pytest.mark.asyncio
async def test_not_my_request_is_403_without_upload(act_as, world, db_session_factory):
    client = await act_as(42)
    r = await _post(client)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "not_assigned"
    world["media"].upload_report_media.assert_not_awaited()
    assert await _status(db_session_factory) == C.REQUEST_STATUS_IN_PROGRESS


@pytest.mark.asyncio
async def test_no_active_shift_is_403_without_upload(act_as, world, db_session_factory):
    async with db_session_factory() as s:
        req = await s.get(Request, NUMBER)
        req.executor_id = 43
        a = (await s.get(RequestAssignment, 1))
        a.executor_id = 43
        await s.commit()
    client = await act_as(43)
    r = await _post(client)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "no_active_shift"
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [C.REQUEST_STATUS_PURCHASE, C.REQUEST_STATUS_CLARIFICATION])
async def test_wrong_status_is_409_without_upload(act_as, world, db_session_factory, status):
    async with db_session_factory() as s:
        (await s.get(Request, NUMBER)).status = status
        await s.commit()
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "invalid_status"
    world["media"].upload_report_media.assert_not_awaited()
    assert await _status(db_session_factory) == status


@pytest.mark.asyncio
async def test_concurrent_attempt_is_409_in_progress(act_as, world):
    await idem.acquire_lock(NUMBER)  # держит «первый» запрос
    client = await act_as(41)
    r = await _post(client)
    assert r.status_code == 409 and r.json()["detail"] == "in_progress"
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_down_still_completes(act_as, world, monkeypatch, db_session_factory):
    """Fail-open: недоступный Redis не мешает закрыть заявку."""
    async def broken():
        return BrokenRedis()
    monkeypatch.setattr(idem, "get_redis", broken)
    client = await act_as(41)
    assert (await _post(client)).status_code == 200
    assert await _status(db_session_factory) == C.REQUEST_STATUS_EXECUTED


@pytest.mark.asyncio
@pytest.mark.parametrize("photo, code, detail", [
    (b"", 422, "photo_empty"),
    (b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 32, 415, "unsupported_photo_type"),
    (b"<html>not an image</html>", 415, "unsupported_photo_type"),
])
async def test_bad_photo_is_rejected_without_upload(act_as, world, photo, code, detail):
    client = await act_as(41)
    r = await _post(client, photo=photo)
    assert r.status_code == code, r.text
    assert r.json()["detail"] == detail
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_photo_is_413(act_as, world):
    client = await act_as(41)
    r = await _post(client, photo=JPEG + b"0" * completion.COMPLETION_PHOTO_MAX_BYTES)
    assert r.status_code == 413, r.text
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_idempotency_key_is_422(act_as, world):
    client = await act_as(41)
    r = await _post(client, key="not-a-uuid")
    assert r.status_code == 422
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_photo_is_422(act_as, world):
    client = await act_as(41)
    r = await client.post(URL, data={"idempotency_key": KEY})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_requires_executor_role(act_as, manager_user, world):
    client = await act_as(manager_user.id)
    assert (await _post(client)).status_code == 403
    world["media"].upload_report_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_request_is_404(act_as, world):
    client = await act_as(41)
    r = await client.post("/api/v2/requests/260925-999/complete",
                          files={"photo": ("a.jpg", JPEG, "image/jpeg")},
                          data={"idempotency_key": KEY})
    assert r.status_code == 404
    world["media"].upload_report_media.assert_not_awaited()
