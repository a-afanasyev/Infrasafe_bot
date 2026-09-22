"""AUD7-ARCH-01: sync ORM-юниты media — вне event loop, короткими сессиями.

До правки sync SQL (search count/all, upload SELECT канала → INSERT метаданных)
исполнялся прямо в event loop, а upload держал сессию/соединение от SELECT
канала до конца Telegram-загрузки. Здесь проверяется поведение, а не форма:
в какой нити создаётся сессия и сколько сессий открыто, пока Telegram «висит».
"""
import asyncio
import threading
import uuid

import pytest

from access_test_utils import FakeTelegram

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class SessionTracker:
    """Обёртка над SessionLocal: нить создания и число открытых сессий."""

    def __init__(self, real_factory):
        self.real_factory = real_factory
        self.threads: list[int] = []
        self.open = 0
        self.max_open = 0

    def __call__(self, *args, **kwargs):
        session = self.real_factory(*args, **kwargs)
        self.threads.append(threading.get_ident())
        self.open += 1
        self.max_open = max(self.max_open, self.open)
        real_close = session.close
        tracker = self

        def close():
            if not getattr(session, "_tracked_closed", False):
                session._tracked_closed = True
                tracker.open -= 1
            real_close()

        session.close = close
        return session


@pytest.fixture
def requests_channel(tracker):
    """Канал заявок (purpose=requests) — иначе upload падает до Telegram."""
    from app.models.media import MediaChannel

    db = tracker.real_factory()
    try:
        db.add(MediaChannel(channel_name="req", channel_username="@req", channel_id=-200,
                            purpose="requests", category="photo", is_active=True))
        db.commit()
    finally:
        db.close()


async def _until_telegram_entered(task, tg):
    """Ждать входа в Telegram-вызов; если задача упала раньше — поднять её ошибку."""
    waiter = asyncio.create_task(tg.entered.wait())
    done, _ = await asyncio.wait({task, waiter}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
    if task in done:
        waiter.cancel()
        task.result()
        raise AssertionError("задача завершилась, не дойдя до Telegram")
    assert waiter in done, "Telegram-вызов не начался за 5 с"


@pytest.fixture
def tracker(monkeypatch):
    from app.db import database

    t = SessionTracker(database.SessionLocal)
    monkeypatch.setattr(database, "SessionLocal", t)
    return t


def _storage(telegram=None):
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = telegram or FakeTelegram()
    return svc


class GatedTelegram(FakeTelegram):
    """send_photo / get_file_url ждут сигнала теста; фиксируют, что было открыто в момент вызова."""

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self.open_at_call: list[int] = []

    async def _wait(self):
        self.open_at_call.append(self.tracker.open)
        self.entered.set()
        await self.gate.wait()

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        await self._wait()
        return await super().send_photo(chat_id, photo, caption=caption, **kwargs)

    async def get_file_url(self, file_id):
        await self._wait()
        return await super().get_file_url(file_id)


@pytest.mark.asyncio
async def test_search_runs_off_event_loop(tracker):
    from app.services.media_search import MediaSearchService

    loop_thread = threading.get_ident()
    result = await MediaSearchService().search_media(query="x", limit=5)

    assert result["total_count"] >= 0
    assert tracker.threads, "поиск обязан открыть сессию"
    assert all(t != loop_thread for t in tracker.threads), "sync SQL поиска выполнился в event loop"
    assert tracker.open == 0


@pytest.mark.asyncio
async def test_upload_persists_off_loop_and_holds_no_session_during_telegram(tracker, requests_channel):
    from app.db.database import SessionLocal, engine
    from app.models.media import MediaFile

    tg = GatedTelegram(tracker)
    svc = _storage(tg)
    loop_thread = threading.get_ident()

    task = asyncio.create_task(svc.upload_request_media(
        request_number="250101-777", file_data=PNG_1x1, filename="a.png",
        content_type="image/png", category="request_photo", tags=["t1"], uploaded_by=1,
    ))
    await _until_telegram_entered(task, tg)

    assert tg.open_at_call == [0], "во время Telegram-загрузки открыта сессия БД"
    assert engine.pool.checkedout() == 0, "соединение удерживается во время Telegram-загрузки"

    tg.gate.set()
    media_file = await asyncio.wait_for(task, 5)

    assert media_file.id and media_file.request_number == "250101-777"
    assert all(t != loop_thread for t in tracker.threads), "ORM-юниты upload выполнились в event loop"
    assert tracker.open == 0
    db = SessionLocal.real_factory() if hasattr(SessionLocal, "real_factory") else SessionLocal()
    try:
        assert db.query(MediaFile).filter(MediaFile.id == media_file.id).count() == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_upload_telegram_failure_leaves_no_open_session(tracker, requests_channel):
    class FailingTelegram(FakeTelegram):
        async def send_photo(self, *a, **kw):
            raise RuntimeError("telegram down")

    svc = _storage(FailingTelegram())
    with pytest.raises(RuntimeError):
        await svc.upload_request_media(
            request_number="250101-778", file_data=PNG_1x1, filename="a.png",
            content_type="image/png", category="request_photo",
        )
    assert tracker.open == 0


@pytest.mark.asyncio
async def test_upload_cancelled_during_telegram_leaves_no_open_session(tracker, requests_channel):
    from app.db.database import engine

    tg = GatedTelegram(tracker)
    svc = _storage(tg)
    task = asyncio.create_task(svc.upload_request_media(
        request_number="250101-779", file_data=PNG_1x1, filename="a.png",
        content_type="image/png", category="request_photo",
    ))
    await _until_telegram_entered(task, tg)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert tracker.open == 0
    assert engine.pool.checkedout() == 0


@pytest.mark.asyncio
async def test_archive_saga_holds_no_session_during_telegram(tracker):
    from app.models.media import MediaChannel, MediaFile

    real = tracker.real_factory
    db = real()
    try:
        db.add(MediaChannel(channel_name="arch", channel_username="@arch", channel_id=-100,
                            purpose="archive", category="mixed", is_active=True))
        mf = MediaFile(telegram_channel_id=-1, telegram_message_id=1,
                       telegram_file_id=f"F-{uuid.uuid4().hex[:8]}", file_type="photo",
                       original_filename="a.png", file_size=1, mime_type="image/png",
                       request_number="250101-780", uploaded_by_user_id=1,
                       category="request_photo", tags=[], upload_source="api", status="active")
        db.add(mf)
        db.commit()
        media_id = mf.id
    finally:
        db.close()

    tg = GatedTelegram(tracker)
    svc = _storage(tg)
    task = asyncio.create_task(svc.archive_media(media_id, "why"))
    await _until_telegram_entered(task, tg)

    assert tg.open_at_call == [0], "фаза 2 саги держит сессию во время Telegram I/O"

    tg.gate.set()
    assert await asyncio.wait_for(task, 5) is True
    assert tracker.open == 0
    db = real()
    try:
        assert db.query(MediaFile.status).filter(MediaFile.id == media_id).scalar() == "archived"
    finally:
        db.close()


# A9-P2-12: остаток AUD7-ARCH-01 — три async-ручки исполняли `db.query` прямо в
# event loop (сессия из Depends(get_db) создаётся в threadpool, но сам SQL —
# в цикле). Проверяется нить, в которой РЕАЛЬНО идёт запрос к БД.


@pytest.fixture
def sql_threads():
    """Нити, в которых исполняется SQL (событие движка, а не создание сессии)."""
    from sqlalchemy import event
    from app.db.database import engine

    threads: list[int] = []

    def _record(*_args, **_kwargs):
        threads.append(threading.get_ident())

    event.listen(engine, "before_cursor_execute", _record)
    yield threads
    event.remove(engine, "before_cursor_execute", _record)


def _media_row(telegram_file_id: str) -> int:
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    db = SessionLocal()
    try:
        mf = MediaFile(telegram_channel_id=-1, telegram_message_id=1,
                       telegram_file_id=telegram_file_id, file_type="photo",
                       original_filename="a.png", file_size=1, mime_type="image/png",
                       request_number="250101-781", uploaded_by_user_id=1,
                       category="request_photo", tags=[], upload_source="api", status="active")
        db.add(mf)
        db.commit()
        return mf.id
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("path_tpl, expect", [
    ("/api/v1/media/{id}", 200),
    ("/api/v1/media/{id}/url", 200),
    ("/api/v1/media/telegram/{fid}", 200),
    ("/api/v1/media/999999", 404),
    ("/api/v1/media/999999/url", 404),
])
async def test_lookup_handlers_run_sql_off_event_loop(sql_threads, path_tpl, expect):
    import httpx
    from app.main import app
    from app.api.v1.media import get_storage_service

    fid = f"TG-{uuid.uuid4().hex[:10]}"
    media_id = _media_row(fid)
    app.dependency_overrides[get_storage_service] = lambda: _storage()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            sql_threads.clear()
            loop_thread = threading.get_ident()
            resp = await client.get(path_tpl.format(id=media_id, fid=fid),
                                    headers={"X-API-Key": "testkey"})
    finally:
        app.dependency_overrides.pop(get_storage_service, None)

    assert resp.status_code == expect, resp.text
    if expect == 200:
        body = resp.json()
        got_id = body["media_file"]["id"] if "media_file" in body else body.get("id", body.get("media_file_id"))
        assert got_id == media_id
    assert sql_threads, "ручка обязана сходить в БД"
    assert loop_thread not in sql_threads, "sync SQL ручки исполнился в event loop"
