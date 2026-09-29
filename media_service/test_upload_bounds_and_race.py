"""Ревью медиасервиса 2026-09-28: границы входа, гонка дубля, статус в /telegram/*/file.

- uploaded_by / request_number проверяются на входе (422) ДО отправки файла в
  канал: раньше Telegram ID (> INT4) ронял INSERT уже после публикации, и файл
  оставался в канале без строки (C2);
- две параллельные загрузки одних байтов: проигравший INSERT (UNIQUE
  telegram_file_id) перечитывает строку победителя, а не отвечает 500;
- /telegram/{file_id}/file не отдаёт файл, чья строка удалена (soft-delete).

Telegram МОКается (access_test_utils.FakeTelegram).
"""
import pytest
from fastapi.testclient import TestClient

from access_test_utils import FakeTelegram, make_fake_message

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
KEY = {"X-API-Key": "testkey"}
INT4_MAX = 2**31 - 1


@pytest.fixture
def client_and_telegram():
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            yield c, svc.telegram
    finally:
        app.dependency_overrides.clear()


def _upload(client, path="/api/v1/media/upload", **data):
    form = {"request_number": "260928-001", **data}
    return client.post(path, headers=KEY, files={"file": ("p.png", PNG, "image/png")}, data=form)


@pytest.mark.parametrize("path", ["/api/v1/media/upload", "/api/v1/media/upload-report"])
@pytest.mark.parametrize("uploaded_by", [str(INT4_MAX + 1), "6055402868", "0", "-5"])
def test_uploaded_by_out_of_int4_rejected_before_telegram(client_and_telegram, path, uploaded_by):
    client, telegram = client_and_telegram
    resp = _upload(client, path, uploaded_by=uploaded_by)
    assert resp.status_code == 422, resp.text
    assert telegram.send_photo_calls == []


@pytest.mark.parametrize("path", ["/api/v1/media/upload", "/api/v1/media/upload-report"])
def test_request_number_too_long_rejected_before_telegram(client_and_telegram, path):
    client, telegram = client_and_telegram
    resp = _upload(client, path, request_number="X" * 21)
    assert resp.status_code == 422, resp.text
    assert telegram.send_photo_calls == []


def test_upload_access_uploaded_by_out_of_int4_rejected(client_and_telegram, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "channel_access", "@uk_media_access_private")
    client, telegram = client_and_telegram
    resp = client.post(
        "/api/v1/media/upload-access", headers=KEY,
        files={"file": ("p.png", PNG, "image/png")},
        data={"kind": "plate", "ref": "G1|1", "uploaded_by": str(INT4_MAX + 1)},
    )
    assert resp.status_code == 422, resp.text
    assert telegram.send_photo_calls == []


def test_boundary_values_accepted(client_and_telegram):
    client, _ = client_and_telegram
    resp = _upload(client, uploaded_by=str(INT4_MAX), request_number="USER_6055402868")
    assert resp.status_code == 201, resp.text
    assert resp.json()["media_file"]["uploaded_by_user_id"] == INT4_MAX


# ---------- гонка дубля telegram_file_id ----------

def test_concurrent_duplicate_insert_reuses_winner_row(monkeypatch):
    """Проигравший видит «строки нет» (окно между SELECT и INSERT), его INSERT
    падает на UNIQUE — он обязан вернуть строку победителя, не 500."""
    from app.services import media_storage
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    message = make_fake_message(file_id="TGFILE-race")
    persist = dict(
        request_number="260928-002", category="request_photo", description=None,
        tags=None, uploaded_by=1, filename="p.png", content_type="image/png", file_size=10,
    )
    winner = svc._persist_upload_sync(message, **persist)

    real_find = media_storage._find_by_telegram_file_id
    calls = {"n": 0}

    def racy_find(db, telegram_file_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # SELECT проигравшего выполнился до INSERT победителя
        return real_find(db, telegram_file_id)

    monkeypatch.setattr(media_storage, "_find_by_telegram_file_id", racy_find)
    loser = svc._persist_upload_sync(message, **persist)

    assert loser.id == winner.id
    assert calls["n"] == 2  # после IntegrityError — перечитали


# ---------- /telegram/{file_id}/file и статус ----------

def _set_status(media_id, status):
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    with SessionLocal() as db:
        db.query(MediaFile).filter(MediaFile.id == media_id).update({"status": status})
        db.commit()


def test_telegram_file_stream_respects_soft_delete(client_and_telegram):
    client, telegram = client_and_telegram
    body = _upload(client).json()["media_file"]
    fid, media_id = body["telegram_file_id"], body["id"]

    ok = client.get(f"/api/v1/media/telegram/{fid}/file", headers=KEY)
    assert ok.status_code == 200

    _set_status(media_id, "deleted")
    telegram.download_file_calls.clear()
    gone = client.get(f"/api/v1/media/telegram/{fid}/file", headers=KEY)
    assert gone.status_code == 404
    assert telegram.download_file_calls == []


def test_telegram_file_stream_unknown_file_id_still_served(client_and_telegram):
    """Ручной поиск по каналу: file_id, которого нет в БД, отдаётся как раньше."""
    client, telegram = client_and_telegram
    resp = client.get("/api/v1/media/telegram/NOT-IN-DB/file", headers=KEY)
    assert resp.status_code == 200
    assert telegram.download_file_calls == ["NOT-IN-DB"]
