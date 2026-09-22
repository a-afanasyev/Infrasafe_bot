"""A9-P2-15: Bot/AiohttpSession и httpx-клиент — процессные, закрываются на shutdown.

До правки `get_storage_service()` на КАЖДЫЙ запрос строил `MediaStorageService`
→ новый `TelegramClientService` → новый `Bot` с `AiohttpSession`, и никто их не
закрывал; `download_file` открывал новый `httpx.AsyncClient` на каждую попытку.
Здесь проверяется поведение: сколько раз создан Bot/httpx-клиент на N запросов,
закрывает ли lifespan-shutdown общие сессии и нет ли «Unclosed client session».
"""
import gc
import logging
import uuid
import warnings
from types import SimpleNamespace

import httpx
import pytest


@pytest.fixture
def fresh_shared_client(monkeypatch):
    """Процессный клиент пуст на входе и восстанавливается после теста."""
    from app.services import telegram_client as tc

    monkeypatch.setattr(tc, "_shared_client", None)
    return tc


@pytest.fixture
def counting_bot(monkeypatch, fresh_shared_client):
    """Считает конструирования aiogram.Bot внутри telegram_client."""
    tc = fresh_shared_client
    real_bot = tc.Bot
    created = []

    def factory(*args, **kwargs):
        bot = real_bot(*args, **kwargs)
        created.append(bot)
        return bot

    monkeypatch.setattr(tc, "Bot", factory)
    return created


@pytest.mark.asyncio
async def test_storage_service_shares_one_telegram_client(counting_bot):
    from app.api.v1.media import get_storage_service

    services = [await get_storage_service() for _ in range(5)]

    assert len({id(s.telegram) for s in services}) == 1, "Telegram-клиент создаётся на запрос"
    assert len(counting_bot) == 1, f"создано {len(counting_bot)} Bot на 5 запросов"


def _create_media_row(telegram_file_id: str) -> int:
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    db = SessionLocal()
    try:
        mf = MediaFile(telegram_channel_id=-1, telegram_message_id=1,
                       telegram_file_id=telegram_file_id, file_type="photo",
                       original_filename="a.png", file_size=1, mime_type="image/png",
                       request_number="250101-701", uploaded_by_user_id=1,
                       category="request_photo", tags=[], upload_source="api", status="active")
        db.add(mf)
        db.commit()
        return mf.id
    finally:
        db.close()


def test_n_http_requests_create_one_bot(counting_bot):
    """Через настоящий DI FastAPI: N запросов к ручке с get_storage_service → один Bot."""
    from fastapi.testclient import TestClient
    from app.main import app

    fid = f"TG-{uuid.uuid4().hex[:10]}"
    _create_media_row(fid)
    client = TestClient(app)
    for _ in range(4):
        resp = client.get(f"/api/v1/media/telegram/{fid}", headers={"X-API-Key": "testkey"})
        assert resp.status_code == 200, resp.text

    assert len(counting_bot) == 1


@pytest.mark.asyncio
async def test_download_reuses_one_httpx_client(fresh_shared_client, monkeypatch):
    """Попытки и вызовы download_file идут через один httpx-клиент процесса."""
    from app.services.telegram_client import TelegramClientService

    constructed = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            constructed.append(self)
            self.gets = 0

        async def get(self, url, **kwargs):
            self.gets += 1
            if self.gets == 1:
                raise httpx.ConnectError("blip")  # первая попытка — ретрай
            return httpx.Response(200, content=b"ok", headers={"content-type": "image/png"},
                                  request=httpx.Request("GET", "http://x"))

        async def aclose(self):
            pass

    async def ok_get_file(file_id):
        return SimpleNamespace(file_path="photos/1.jpg")

    async def instant_sleep(_d):
        return None

    import asyncio
    monkeypatch.setattr(asyncio, "sleep", instant_sleep)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    svc = TelegramClientService.__new__(TelegramClientService)
    monkeypatch.setattr(svc, "get_file", ok_get_file, raising=False)

    await svc.download_file("F1")
    await svc.download_file("F2")

    assert len(constructed) == 1, f"httpx-клиентов создано: {len(constructed)}"
    assert constructed[0].gets == 3


@pytest.mark.asyncio
async def test_lifespan_shutdown_closes_shared_sessions(fresh_shared_client, caplog):
    """Shutdown закрывает aiohttp-сессию Bot и httpx-клиент; «Unclosed» не всплывает."""
    from app.main import app, lifespan

    tc = fresh_shared_client
    caplog.set_level(logging.ERROR)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async with lifespan(app):
            client = tc.get_telegram_client()
            aio_session = await client.bot.session.create_session()  # как при первом вызове Bot API
            http = client._http_client()
            assert not aio_session.closed
            assert not http.is_closed

        assert aio_session.closed, "aiohttp-сессия Bot не закрыта на shutdown"
        assert http.is_closed, "httpx-клиент не закрыт на shutdown"
        # После shutdown следующий доступ даёт НОВЫЙ клиент, а не закрытый.
        assert tc._shared_client is None

        del client, aio_session, http
        gc.collect()

    unclosed = [w for w in caught if "Unclosed" in str(w.message)]
    assert not unclosed, [str(w.message) for w in unclosed]
    assert "Unclosed client session" not in caplog.text


@pytest.mark.asyncio
async def test_storage_service_close_does_not_close_shared_client(fresh_shared_client):
    """Per-request сервис не владеет общим клиентом — его close() не рвёт сессию."""
    from app.api.v1.media import get_storage_service

    tc = fresh_shared_client
    svc = await get_storage_service()
    aio_session = await svc.telegram.bot.session.create_session()
    try:
        if hasattr(svc, "close"):
            await svc.close()
        assert not aio_session.closed
    finally:
        await tc.close_telegram_client()
    assert aio_session.closed
