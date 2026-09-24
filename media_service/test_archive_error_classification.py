"""A9-P3-34: архивация различает постоянные и транзиентные сбои.

Раньше любое исключение саги архивации → TRANSIENT_FAILURE → 503 «повторите»,
в том числе конфигурационные (нет архивного канала, channel_id=NULL) и отказы
Telegram по существу запроса (400/403 на sendPhoto) — клиент повторял вечно.

Теперь:
  * постоянные (канал не сконфигурирован; TelegramBadRequest/Forbidden/
    NotFound/Unauthorized) → ArchiveFailedError(reason) → HTTP 500 со
    стабильным кодом причины, без сырого текста исключения;
  * транзиентные (TelegramRetryAfter, TelegramNetworkError, 5xx Telegram,
    таймаут, неизвестное) → TRANSIENT_FAILURE → HTTP 503.
В обоих случаях резервирование откатывается: файл остаётся active.
"""
import uuid

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.methods import SendPhoto
from fastapi.testclient import TestClient

from access_test_utils import FakeTelegram

# Текст исключения, похожий на то, что может унести токен/URL: не должен
# попасть в тело HTTP-ответа.
SECRET_TEXT = "https://api.telegram.org/bot123456789:AA-secret-token/sendPhoto"


def _method():
    return SendPhoto(chat_id=-100, photo="x")


def _make_exc(kind: str) -> BaseException:
    if kind == "bad_request":
        return TelegramBadRequest(_method(), f"Bad Request: chat not found {SECRET_TEXT}")
    if kind == "forbidden":
        return TelegramForbiddenError(_method(), f"Forbidden: bot is not a member {SECRET_TEXT}")
    if kind == "not_found":
        return TelegramNotFound(_method(), f"Not Found {SECRET_TEXT}")
    if kind == "unauthorized":
        return TelegramUnauthorizedError(_method(), f"Unauthorized {SECRET_TEXT}")
    if kind == "retry_after":
        return TelegramRetryAfter(_method(), "Too Many Requests", retry_after=5)
    if kind == "network":
        return TelegramNetworkError(_method(), "HTTP Client says - ClientConnectorError")
    if kind == "server":
        return TelegramServerError(_method(), "Internal Server Error")
    if kind == "timeout":
        return TimeoutError()
    raise AssertionError(kind)


PERMANENT_KINDS = ["bad_request", "forbidden", "not_found", "unauthorized"]
TRANSIENT_KINDS = ["retry_after", "network", "server", "timeout"]


class RaisingTelegram(FakeTelegram):
    def __init__(self, exc: BaseException):
        super().__init__()
        self._exc = exc

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.send_photo_calls.append({"chat_id": chat_id, "caption": caption})
        raise self._exc


def _service(telegram):
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = telegram
    return svc


def _create_media_file() -> int:
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    s = SessionLocal()
    try:
        mf = MediaFile(
            telegram_channel_id=-1001111111111,
            telegram_message_id=100,
            telegram_file_id=f"TGFILE-{uuid.uuid4().hex[:12]}",
            file_type="photo",
            original_filename="test.jpg",
            file_size=123,
            mime_type="image/jpeg",
            request_number="250101-001",
            uploaded_by_user_id=1,
            category="request_photo",
            status="active",
            publication_locked=False,
            upload_source="test",
        )
        s.add(mf)
        s.commit()
        return mf.id
    finally:
        s.close()


def _create_archive_channel(channel_id=-1009999999999, channel_username="@archive_test"):
    from app.db.database import SessionLocal
    from app.models.media import MediaChannel

    s = SessionLocal()
    try:
        s.add(MediaChannel(
            channel_name="uk_media_archive_test",
            channel_id=channel_id,
            channel_username=channel_username,
            purpose="archive",
            category="mixed",
            is_active=True,
        ))
        s.commit()
    finally:
        s.close()


def _status(media_id: int) -> str:
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    s = SessionLocal()
    try:
        return s.query(MediaFile).filter(MediaFile.id == media_id).one().status
    finally:
        s.close()


def _post_archive(svc, media_id: int):
    from app.main import app
    from app.api.v1.media import get_storage_service

    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        return TestClient(app).post(
            f"/api/v1/media/{media_id}/archive",
            headers={"X-API-Key": "testkey"},
            json={},
        )
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


# ---------- сервис: постоянные сбои ----------

@pytest.mark.asyncio
async def test_archive_without_archive_channel_is_permanent():
    from app.services.media_storage import ArchiveFailedError

    svc = _service(FakeTelegram())
    media_id = _create_media_file()

    with pytest.raises(ArchiveFailedError) as ei:
        await svc.archive_media(media_id)

    assert ei.value.reason == "archive_channel_not_configured"
    assert svc.telegram.send_photo_calls == []
    assert _status(media_id) == "active"


@pytest.mark.asyncio
async def test_archive_channel_without_id_and_username_is_permanent():
    """Находка QA: channel_id=NULL (и нет username) — конфиг-ошибка, не «повторите»."""
    from app.services.media_storage import ArchiveFailedError

    _create_archive_channel(channel_id=None, channel_username="")
    svc = _service(FakeTelegram())
    media_id = _create_media_file()

    with pytest.raises(ArchiveFailedError) as ei:
        await svc.archive_media(media_id)

    assert ei.value.reason == "archive_channel_not_configured"
    assert svc.telegram.send_photo_calls == []
    assert _status(media_id) == "active"


@pytest.mark.asyncio
async def test_archive_channel_without_id_falls_back_to_username():
    """Как и загрузка (_upload_to_channel): numeric id ещё не известен —
    шлём по username, а не chat_id=None."""
    from app.services.media_storage import MediaRemovalOutcome

    _create_archive_channel(channel_id=None, channel_username="@archive_test")
    svc = _service(FakeTelegram())
    media_id = _create_media_file()

    assert await svc.archive_media(media_id) is MediaRemovalOutcome.DONE
    assert svc.telegram.send_photo_calls[0]["chat_id"] == "@archive_test"
    assert _status(media_id) == "archived"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", PERMANENT_KINDS)
async def test_archive_telegram_rejection_is_permanent(kind):
    from app.services.media_storage import ArchiveFailedError

    _create_archive_channel()
    svc = _service(RaisingTelegram(_make_exc(kind)))
    media_id = _create_media_file()

    with pytest.raises(ArchiveFailedError) as ei:
        await svc.archive_media(media_id)

    assert ei.value.reason == "archive_rejected_by_telegram"
    assert _status(media_id) == "active"


# ---------- сервис: транзиентные сбои ----------

@pytest.mark.asyncio
@pytest.mark.parametrize("kind", TRANSIENT_KINDS)
async def test_archive_transient_telegram_failure_stays_transient(kind):
    from app.services.media_storage import MediaRemovalOutcome

    _create_archive_channel()
    svc = _service(RaisingTelegram(_make_exc(kind)))
    media_id = _create_media_file()

    assert await svc.archive_media(media_id) is MediaRemovalOutcome.TRANSIENT_FAILURE
    assert _status(media_id) == "active"


# ---------- endpoint ----------

@pytest.mark.parametrize("kind", PERMANENT_KINDS)
def test_archive_endpoint_permanent_rejection_returns_500_with_code(kind):
    _create_archive_channel()
    media_id = _create_media_file()

    resp = _post_archive(_service(RaisingTelegram(_make_exc(kind))), media_id)

    assert resp.status_code == 500, resp.text
    assert resp.json()["message"].startswith("archive_rejected_by_telegram:")
    assert "secret-token" not in resp.text
    assert "api.telegram.org" not in resp.text
    assert _status(media_id) == "active"


def test_archive_endpoint_channel_not_configured_returns_500_with_code():
    media_id = _create_media_file()

    resp = _post_archive(_service(FakeTelegram()), media_id)

    assert resp.status_code == 500, resp.text
    assert resp.json()["message"].startswith("archive_channel_not_configured:")
    assert _status(media_id) == "active"


@pytest.mark.parametrize("kind", TRANSIENT_KINDS)
def test_archive_endpoint_transient_failure_returns_503(kind):
    _create_archive_channel()
    media_id = _create_media_file()

    resp = _post_archive(_service(RaisingTelegram(_make_exc(kind))), media_id)

    assert resp.status_code == 503, resp.text
    assert _status(media_id) == "active"
