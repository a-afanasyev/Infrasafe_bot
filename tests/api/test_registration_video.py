"""Кнопка «🎬 Видео о регистрации» в карточке жителя (решение владельца 2026-11-05).

Сеть — через `telegram_api` (MockTransport общего клиента api/telegram_send):
проверяется реальный запрос sendVideo — по file_id из кэша бота или загрузкой
файла (multipart), а не «эндпоинт ответил 200».
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.user import User
from uk_management_bot.services import tutorial_videos

FILE_ID = "FID-registration-ru"


class FakeRedis:
    def __init__(self):
        self.store: dict = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = value


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()

    async def get_redis():
        return fake

    monkeypatch.setattr(tutorial_videos, "_get_redis", get_redis)
    return fake


def _key(language="ru"):
    return tutorial_videos.file_id_cache_key(tutorial_videos.video_path("registration", language))


async def _resident(db, tg, **fields):
    fields.setdefault("language", "ru")
    u = User(telegram_id=tg, first_name="R", roles='["applicant"]', active_role="applicant",
             status="pending", verification_status="pending", **fields)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _video_ok(request):
    import httpx

    return httpx.Response(200, json={"ok": True, "result": {"video": {"file_id": FILE_ID}}})


def _send_video_requests(telegram_api):
    return [r for r in telegram_api.requests if r.url.path.endswith("/sendVideo")]


async def _sent_at(db, user_id):
    db.expire_all()
    return (await db.execute(
        select(User.registration_video_sent_at).where(User.id == user_id))).scalar_one()


@pytest.mark.asyncio
async def test_first_send_uploads_file_and_caches_file_id(client, db_session, telegram_api, redis):
    resident_id = (await _resident(db_session, 8101)).id
    telegram_api.handler = _video_ok

    resp = await client.post(f"/api/v2/residents/{resident_id}/send-registration-video")

    assert resp.status_code == 200, resp.text
    [req] = _send_video_requests(telegram_api)
    assert req.headers["content-type"].startswith("multipart/form-data")
    assert b'name="video"; filename="registration_ru.mp4"' in req.content
    assert b"8101" in req.content
    assert redis.store[_key()] == FILE_ID
    assert await _sent_at(db_session, resident_id) is not None


@pytest.mark.asyncio
async def test_cached_file_id_is_sent_without_upload(client, db_session, telegram_api, redis):
    resident = await _resident(db_session, 8102, language="uz_cyrl")
    redis.store[_key("uz")] = FILE_ID
    telegram_api.handler = _video_ok

    resp = await client.post(f"/api/v2/residents/{resident.id}/send-registration-video")

    assert resp.status_code == 200
    [body] = telegram_api.calls("sendVideo")
    assert body["video"] == FILE_ID and body["chat_id"] == 8102


@pytest.mark.asyncio
async def test_stale_file_id_falls_back_to_upload(client, db_session, telegram_api, redis):
    import httpx

    resident = await _resident(db_session, 8103)
    redis.store[_key()] = "FID-stale"

    def handler(request):
        if b"FID-stale" in request.content:
            return httpx.Response(400, json={"ok": False, "description": "Bad Request: wrong file identifier"})
        return _video_ok(request)

    telegram_api.handler = handler
    resp = await client.post(f"/api/v2/residents/{resident.id}/send-registration-video")

    assert resp.status_code == 200
    assert len(_send_video_requests(telegram_api)) == 2
    assert redis.store[_key()] == FILE_ID


@pytest.mark.asyncio
async def test_second_send_within_a_day_is_409(client, db_session, telegram_api, redis):
    resident = await _resident(
        db_session, 8104, registration_video_sent_at=datetime.now(timezone.utc) - timedelta(hours=2))

    resp = await client.post(f"/api/v2/residents/{resident.id}/send-registration-video")

    assert resp.status_code == 409
    assert "сутки" in resp.json()["detail"]
    assert _send_video_requests(telegram_api) == []


@pytest.mark.asyncio
async def test_resend_allowed_after_a_day(client, db_session, telegram_api, redis):
    resident = await _resident(
        db_session, 8105, registration_video_sent_at=datetime.now(timezone.utc) - timedelta(days=1, minutes=1))
    telegram_api.handler = _video_ok

    resp = await client.post(f"/api/v2/residents/{resident.id}/send-registration-video")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_blocked_bot_is_409_and_stamps_blocked_not_sent(client, db_session, telegram_api, redis):
    resident_id = (await _resident(db_session, 8106)).id
    telegram_api.reply(403, description="Forbidden: bot was blocked by the user")

    resp = await client.post(f"/api/v2/residents/{resident_id}/send-registration-video")

    assert resp.status_code == 409
    assert "заблокировал" in resp.json()["detail"]
    assert await _sent_at(db_session, resident_id) is None
    blocked = (await db_session.execute(
        select(User.bot_blocked_at).where(User.id == resident_id))).scalar_one()
    assert blocked is not None


@pytest.mark.asyncio
async def test_unknown_resident_404(client, telegram_api, redis):
    resp = await client.post("/api/v2/residents/999999/send-registration-video")
    assert resp.status_code == 404
    assert _send_video_requests(telegram_api) == []


@pytest.mark.asyncio
async def test_sent_at_is_listed(client, db_session, telegram_api, redis):
    resident = await _resident(db_session, 8107)
    telegram_api.handler = _video_ok
    assert (await client.post(f"/api/v2/residents/{resident.id}/send-registration-video")).status_code == 200

    items = (await client.get("/api/v2/residents", params={"limit": 100})).json()["items"]
    row = next(i for i in items if i["id"] == resident.id)
    assert row["registration_video_sent_at"] is not None
