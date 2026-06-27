"""Тесты домен-нейтральной access-загрузки (контроль доступа).

Покрытие:
  - upload_domain_media: plate/overview → канал «access» + правильная category;
  - нет CHANNEL_ACCESS → понятная ошибка (ChannelNotConfiguredError → 503);
  - request_number у access-файла = None (домен-нейтральный, ref хранится в тегах);
  - endpoint POST /media/upload-access: требует API-ключ, 201 с MediaUploadResponse,
    503 при незаконфигуренном канале.

Telegram МОКается (см. access_test_utils.FakeTelegram).
"""
import pytest
from fastapi.testclient import TestClient

from access_test_utils import FakeTelegram

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_service(channel_access="@uk_media_access_private", monkeypatch=None):
    """Создаёт MediaStorageService с фейковым Telegram и заданным channel_access."""
    from app.services.media_storage import MediaStorageService
    from app.core.config import settings

    if monkeypatch is not None:
        monkeypatch.setattr(settings, "channel_access", channel_access)
    else:
        settings.channel_access = channel_access

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    svc.channels_cache = {}
    return svc


# ---------- service-level ----------

@pytest.mark.asyncio
async def test_upload_access_plate_uses_access_channel_and_category(monkeypatch):
    from app.core.config import TelegramChannels, FileCategories

    svc = _make_service(monkeypatch=monkeypatch)
    media = await svc.upload_domain_media(
        channel_purpose=TelegramChannels.ACCESS,
        category=FileCategories.ACCESS_PLATE,
        ref="GATE1|evt-42",
        file_data=PNG_1x1,
        filename="plate.png",
        content_type="image/png",
        uploaded_by=10,
    )

    assert media.category == "access_plate"
    # файл ушёл именно в access-канал (send_photo вызван 1 раз)
    assert len(svc.telegram.send_photo_calls) == 1

    # в БД создан канал с purpose=access
    from app.db.database import SessionLocal
    from app.models.media import MediaChannel
    s = SessionLocal()
    try:
        ch = s.query(MediaChannel).filter(MediaChannel.purpose == "access").first()
        assert ch is not None
        assert ch.channel_username == "@uk_media_access_private"
    finally:
        s.close()


@pytest.mark.asyncio
async def test_upload_access_overview_category(monkeypatch):
    from app.core.config import TelegramChannels, FileCategories

    svc = _make_service(monkeypatch=monkeypatch)
    media = await svc.upload_domain_media(
        channel_purpose=TelegramChannels.ACCESS,
        category=FileCategories.ACCESS_OVERVIEW,
        ref="GATE1|evt-43",
        file_data=PNG_1x1,
        filename="overview.png",
        content_type="image/png",
    )
    assert media.category == "access_overview"


@pytest.mark.asyncio
async def test_access_ref_stored_and_request_number_nullable(monkeypatch):
    """ref домен-нейтрален: хранится в тегах, request_number остаётся None."""
    from app.core.config import TelegramChannels, FileCategories

    svc = _make_service(monkeypatch=monkeypatch)
    media = await svc.upload_domain_media(
        channel_purpose=TelegramChannels.ACCESS,
        category=FileCategories.ACCESS_PLATE,
        ref="CTRL-7|999",
        file_data=PNG_1x1,
        filename="p.png",
        content_type="image/png",
    )
    assert media.request_number is None
    assert "ref:CTRL-7|999" in (media.tags or [])


@pytest.mark.asyncio
async def test_access_channel_not_configured_raises(monkeypatch):
    from app.core.config import TelegramChannels, FileCategories
    from app.services.media_storage import ChannelNotConfiguredError

    svc = _make_service(channel_access="", monkeypatch=monkeypatch)
    with pytest.raises(ChannelNotConfiguredError):
        await svc.upload_domain_media(
            channel_purpose=TelegramChannels.ACCESS,
            category=FileCategories.ACCESS_PLATE,
            ref="X|1",
            file_data=PNG_1x1,
            filename="p.png",
            content_type="image/png",
        )
    # ничего не отправлено в Telegram
    assert svc.telegram.send_photo_calls == []


# ---------- endpoint-level ----------

@pytest.fixture
def client_and_service(monkeypatch):
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService
    from app.core.config import settings

    monkeypatch.setattr(settings, "channel_access", "@uk_media_access_private")

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    svc.channels_cache = {}
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            yield c, svc
    finally:
        app.dependency_overrides.clear()


def test_endpoint_requires_api_key(client_and_service):
    client, _ = client_and_service
    resp = client.post(
        "/api/v1/media/upload-access",
        files={"file": ("p.png", PNG_1x1, "image/png")},
        data={"kind": "plate", "ref": "G1|1"},
    )
    assert resp.status_code == 401


def test_endpoint_upload_access_plate_ok(client_and_service):
    client, svc = client_and_service
    resp = client.post(
        "/api/v1/media/upload-access",
        headers={"X-API-Key": "testkey"},
        files={"file": ("p.png", PNG_1x1, "image/png")},
        data={"kind": "plate", "ref": "G1|evt-1", "uploaded_by": "5"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["media_file"]["category"] == "access_plate"
    assert body["media_file"]["telegram_file_id"]
    assert body["file_url"].endswith("/file")
    assert len(svc.telegram.send_photo_calls) == 1


def test_endpoint_upload_access_overview_ok(client_and_service):
    client, _ = client_and_service
    resp = client.post(
        "/api/v1/media/upload-access",
        headers={"X-API-Key": "testkey"},
        files={"file": ("o.png", PNG_1x1, "image/png")},
        data={"kind": "overview", "ref": "G1|evt-2"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["media_file"]["category"] == "access_overview"


def test_endpoint_invalid_kind_rejected(client_and_service):
    client, _ = client_and_service
    resp = client.post(
        "/api/v1/media/upload-access",
        headers={"X-API-Key": "testkey"},
        files={"file": ("o.png", PNG_1x1, "image/png")},
        data={"kind": "bogus", "ref": "G1|evt-2"},
    )
    assert resp.status_code == 400


def test_endpoint_access_not_configured_returns_503(monkeypatch):
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService
    from app.core.config import settings

    monkeypatch.setattr(settings, "channel_access", "")
    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    svc.channels_cache = {}
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/media/upload-access",
                headers={"X-API-Key": "testkey"},
                files={"file": ("p.png", PNG_1x1, "image/png")},
                data={"kind": "plate", "ref": "G1|1"},
            )
        assert resp.status_code == 503, resp.text
        assert "access" in resp.json()["message"].lower()
    finally:
        app.dependency_overrides.clear()


# ---------- regression: request-флоу не сломан ----------

def test_request_upload_flow_still_works(monkeypatch):
    """Старый endpoint /media/upload должен работать как раньше (мок Telegram)."""
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    svc.channels_cache = {}
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/media/upload",
                headers={"X-API-Key": "testkey"},
                files={"file": ("r.png", PNG_1x1, "image/png")},
                data={"request_number": "250101-001", "category": "request_photo"},
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["media_file"]["request_number"] == "250101-001"
        assert body["media_file"]["category"] == "request_photo"
    finally:
        app.dependency_overrides.clear()
