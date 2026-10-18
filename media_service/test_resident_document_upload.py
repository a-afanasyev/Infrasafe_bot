"""Узкий приём зашифрованных документов жителей (`/upload-resident-document`).

Бот шифрует скан до отправки — сюда приходит непрозрачный blob. Сервис не
сниффит тип, хранит `application/octet-stream`, имя назначает сам
(`<uuid>.bin`), подпись — без персональных данных; общий `/upload` и его
allowlist не расширяются.
"""
import re

import pytest
from fastapi.testclient import TestClient

from access_test_utils import FakeTelegram

BLOB = b"v1" + bytes(range(200))  # шифротекст: ни одной медиа-сигнатуры


@pytest.fixture
def client_and_service(monkeypatch):
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService
    from app.core.config import settings

    monkeypatch.setattr(settings, "channel_archive", "@uk_media_archive_private")

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            yield c, svc
    finally:
        app.dependency_overrides.clear()


def _post(client, data=BLOB, filename="Иванов_паспорт.pdf", **form):
    return client.post(
        "/api/v1/media/upload-resident-document",
        headers={"X-API-Key": "testkey"},
        files={"file": (filename, data, "application/pdf")},
        data={"uploaded_by": "5", **form},
    )


def test_requires_api_key(client_and_service):
    client, _ = client_and_service
    resp = client.post(
        "/api/v1/media/upload-resident-document",
        files={"file": ("x.bin", BLOB, "application/octet-stream")},
    )
    assert resp.status_code == 401


def test_blob_stored_as_opaque_document(client_and_service):
    client, svc = client_and_service
    resp = _post(client)
    assert resp.status_code == 201, resp.text
    media = resp.json()["media_file"]
    assert media["category"] == "resident_document"
    assert media["mime_type"] == "application/octet-stream"
    # исходное имя (ФИО, тип документа) не попадает ни в БД, ни в Telegram
    assert re.fullmatch(r"[0-9a-f]{32}\.bin", media["original_filename"])
    assert media["request_number"] is None
    # не image/* → send_document: Telegram не пережимает байты
    assert svc.telegram.send_photo_calls == []
    assert len(svc.telegram.send_document_calls) == 1
    caption = svc.telegram.send_document_calls[0]["caption"] or ""
    assert "Иванов" not in caption and "паспорт" not in caption


def test_two_uploads_get_distinct_rows(client_and_service):
    client, _ = client_and_service
    first = _post(client).json()["media_file"]["id"]
    second = _post(client).json()["media_file"]["id"]
    assert first != second


def test_size_limit_still_enforced(client_and_service, monkeypatch):
    from app.core.config import settings

    client, svc = client_and_service
    monkeypatch.setattr(settings, "max_file_size", 100)
    resp = _post(client)
    assert resp.status_code == 400
    assert svc.telegram.send_document_calls == []


def test_archive_channel_not_configured_is_503(client_and_service, monkeypatch):
    from app.core.config import settings

    client, svc = client_and_service
    monkeypatch.setattr(settings, "channel_archive", "")
    resp = _post(client)
    assert resp.status_code == 503
    assert svc.telegram.send_document_calls == []


def test_general_upload_still_rejects_octet_stream(client_and_service):
    """Общий allowlist не расширен: на /upload непрозрачный blob не проходит."""
    client, _ = client_and_service
    resp = client.post(
        "/api/v1/media/upload",
        headers={"X-API-Key": "testkey"},
        files={"file": ("x.bin", BLOB, "application/octet-stream")},
        data={"request_number": "251018-001", "category": "request_photo"},
    )
    assert resp.status_code in (400, 415)


def test_category_has_enum_member_and_archive_channel():
    from app.core.config import FileCategories, TelegramChannels
    from app.schemas.media import MediaCategoryEnum

    assert FileCategories.RESIDENT_DOCUMENT == "resident_document"
    assert MediaCategoryEnum.RESIDENT_DOCUMENT.value == "resident_document"
    assert FileCategories.CATEGORY_TO_CHANNEL[FileCategories.RESIDENT_DOCUMENT] == TelegramChannels.ARCHIVE
