"""Telegram ID загрузившего рядом с users.id (решение владельца 2026-09-29).

- /upload и /upload-report принимают uploaded_by_telegram_id (BIGINT), ответ
  его возвращает, ручной поиск фильтрует по нему;
- миграция 0002 на существующей БД добавляет колонку и заполняет её у
  документов пользователей (request_number USER_<tg>), повторный прогон ничего
  не меняет — на настоящем PostgreSQL.
"""
import os
import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from access_test_utils import FakeTelegram

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
KEY = {"X-API-Key": "testkey"}
BIG_TG = 6055402868


@pytest.fixture
def client():
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["/api/v1/media/upload", "/api/v1/media/upload-report"])
def test_upload_stores_both_ids(client, path):
    resp = client.post(path, headers=KEY, files={"file": ("p.png", PNG, "image/png")},
                       data={"request_number": f"USER_{BIG_TG}", "uploaded_by": "53",
                             "uploaded_by_telegram_id": str(BIG_TG)})
    assert resp.status_code == 201, resp.text
    body = resp.json()["media_file"]
    assert body["uploaded_by_user_id"] == 53
    assert body["uploaded_by_telegram_id"] == BIG_TG


def test_telegram_id_optional(client):
    resp = client.post("/api/v1/media/upload", headers=KEY, files={"file": ("p.png", PNG, "image/png")},
                       data={"request_number": "260929-001", "uploaded_by": "7"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["media_file"]["uploaded_by_telegram_id"] is None


def test_search_by_telegram_id(client):
    for n, tg in ((1, BIG_TG), (2, 111)):
        png = PNG + bytes([n])
        r = client.post("/api/v1/media/upload", headers=KEY, files={"file": (f"{n}.png", png, "image/png")},
                        data={"request_number": f"USER_{tg}", "uploaded_by": str(n),
                              "uploaded_by_telegram_id": str(tg)})
        assert r.status_code == 201, r.text
    res = client.get("/api/v1/media/search", headers=KEY, params={"uploaded_by_telegram_id": BIG_TG})
    assert res.status_code == 200, res.text
    assert [r["request_number"] for r in res.json()["results"]] == [f"USER_{BIG_TG}"]


# ---------- миграция 0002 на существующей БД (PostgreSQL) ----------

PG_URL = os.environ.get("MEDIA_PG_DRIFT_URL")
ROOT = pathlib.Path(__file__).parent


@pytest.mark.skipif(not PG_URL, reason="MEDIA_PG_DRIFT_URL не задан (только PostgreSQL)")
def test_migration_backfills_user_documents_idempotently():
    from run_migrations import apply_migrations

    schema = "tgid_backfill_test"
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin.dispose()
    engine = create_engine(PG_URL, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as conn:
            # Прод-схема до 0001 + строки «как на проде»: документ и фото заявки.
            conn.execute(text((ROOT / "schema_baseline" / "pre_0001.sql").read_text()))
            conn.execute(text(
                "INSERT INTO media_files (telegram_channel_id, telegram_message_id, telegram_file_id,"
                " file_type, request_number, uploaded_by_user_id, category) VALUES"
                " (-100, 1, 'F1', 'photo', 'USER_6055402868', 53, 'archive'),"
                " (-100, 2, 'F2', 'photo', '260929-001', 7, 'request_photo')"
            ))
        for _ in range(2):  # повторный прогон — на каждом деплое
            with engine.begin() as conn:
                apply_migrations(conn)
        with engine.connect() as conn:
            rows = dict(conn.execute(text(
                "SELECT telegram_file_id, uploaded_by_telegram_id FROM media_files"
            )).all())
        assert rows == {"F1": BIG_TG, "F2": None}
    finally:
        engine.dispose()


def test_reupload_same_file_fills_missing_telegram_id(client):
    """Строка создана без Telegram ID (до фичи) — повторная загрузка того же
    файла тем же владельцем его дописывает; чужую заявку не трогает."""
    from access_test_utils import make_fake_message
    from app.api.v1.media import get_storage_service

    fixed = make_fake_message(file_id="TG-SAME-DOC")

    async def same_photo(*args, **kwargs):
        return fixed

    # Telegram отдаёт один и тот же file_id для одних байтов — эмулируем.
    storage = client.app.dependency_overrides[get_storage_service]()
    storage.telegram.send_photo = same_photo

    form = {"request_number": f"USER_{BIG_TG}", "uploaded_by": "53"}
    first = client.post("/api/v1/media/upload", headers=KEY, files={"file": ("p.png", PNG, "image/png")}, data=form)
    assert first.json()["media_file"]["uploaded_by_telegram_id"] is None

    other = client.post("/api/v1/media/upload", headers=KEY, files={"file": ("p.png", PNG, "image/png")},
                        data={"request_number": "USER_1", "uploaded_by": "9", "uploaded_by_telegram_id": "1"})
    assert other.json()["media_file"]["uploaded_by_telegram_id"] is None

    again = client.post("/api/v1/media/upload", headers=KEY, files={"file": ("p.png", PNG, "image/png")},
                        data={**form, "uploaded_by_telegram_id": str(BIG_TG)})
    assert again.status_code == 201, again.text
    assert again.json()["media_file"]["id"] == first.json()["media_file"]["id"]
    assert again.json()["media_file"]["uploaded_by_telegram_id"] == BIG_TG


def test_search_rejects_nonpositive_telegram_id(client):
    res = client.get("/api/v1/media/search", headers=KEY, params={"uploaded_by_telegram_id": 0})
    assert res.status_code == 422
