"""Тесты превью-кэша и ограничителя скачиваний (инцидент 2026-07-25).

Что случилось: публичная витрина «до/после» на 30 карточках запрашивала 60
оригиналов, каждый — скачивание из Telegram (~1 с) при УДЕРЖИВАЕМОМ соединении
к БД. Пул 5+10 выедался, запросы вставали на 30 с и падали в 504 — вместе с
приватными фото заявок, которые ходят через тот же эндпоинт.

Здесь проверяется всё, что этому противопоставлено: превью вместо оригинала,
дисковый кэш с вытеснением по заявкам, семафор на скачивания и — главное —
что эндпоинты больше не держат сессию БД сквозь сетевой I/O.
"""
import asyncio
import inspect
import io
import os
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from access_test_utils import FakeTelegram


def _real_png(w=1600, h=1200, colour=(120, 90, 60)) -> bytes:
    """Настоящее изображение — FakeTelegram по умолчанию отдаёт байты, которые
    Pillow открыть не может, а нам нужен путь, где превью реально строится."""
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


class ImageTelegram(FakeTelegram):
    """FakeTelegram, отдающий валидный PNG заданного размера."""

    def __init__(self, image: bytes | None = None):
        super().__init__()
        self.image = image if image is not None else _real_png()

    async def download_file(self, file_id):
        self.download_file_calls.append(file_id)
        return self.image, "image/png"


def _create_media_file(**overrides) -> int:
    from app.db.database import SessionLocal
    from app.models.media import MediaFile
    import uuid

    defaults = dict(
        telegram_channel_id=-1001111111111,
        telegram_message_id=100,
        telegram_file_id=f"TGFILE-{uuid.uuid4().hex[:12]}",
        file_type="photo",
        original_filename="test.png",
        file_size=123,
        mime_type="image/png",
        request_number="250101-001",
        uploaded_by_user_id=1,
        category="request_photo",
        status="active",
        publication_locked=False,
        upload_source="test",
    )
    defaults.update(overrides)
    s = SessionLocal()
    try:
        mf = MediaFile(**defaults)
        s.add(mf)
        s.commit()
        s.refresh(mf)
        return mf.id
    finally:
        s.close()


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    from app.core.config import settings

    d = tmp_path / "preview-cache"
    d.mkdir()
    monkeypatch.setattr(settings, "preview_cache_dir", str(d))
    yield str(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def client_with(monkeypatch, cache_dir):
    """TestClient с подменённым Telegram; возвращает фабрику."""
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService

    created = []

    def make(telegram=None):
        svc = MediaStorageService.__new__(MediaStorageService)
        svc.telegram = telegram or ImageTelegram()
        svc.channels_cache = {}
        app.dependency_overrides[get_storage_service] = lambda: svc
        c = TestClient(app)
        c.__enter__()
        created.append(c)
        return c, svc

    yield make
    for c in created:
        c.__exit__(None, None, None)
    app.dependency_overrides.clear()


# ── превью ───────────────────────────────────────────────────────────


def test_preview_is_smaller_jpeg(client_with):
    client, svc = client_with()
    media_id = _create_media_file()

    resp = client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert len(resp.content) < len(svc.telegram.image)
    with Image.open(io.BytesIO(resp.content)) as img:
        from app.core.config import settings
        assert max(img.size) <= settings.preview_max_px


def test_preview_second_request_does_not_touch_telegram(client_with):
    """Смысл кэша: повторный просмотр витрины не стоит ни одного скачивания."""
    client, svc = client_with()
    media_id = _create_media_file()

    first = client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})
    second = client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})

    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert len(svc.telegram.download_file_calls) == 1


def test_non_image_falls_back_to_original_and_is_not_cached(client_with, cache_dir):
    """Видео/документ уменьшать нечем — отдаём как есть, но кэш не засоряем."""
    client, svc = client_with(telegram=FakeTelegram())  # отдаёт не-изображение
    media_id = _create_media_file(file_type="video", mime_type="video/mp4")

    resp = client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})

    assert resp.status_code == 200
    assert resp.content == b"\x89PNG\r\n\x1a\nfakebytes"
    assert os.listdir(cache_dir) == []


def test_preview_404_for_deleted_file(client_with):
    client, _ = client_with()
    media_id = _create_media_file(status="deleted")

    resp = client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 404


def test_preview_502_when_source_unavailable(client_with):
    """Недоступный Telegram — это 502 (проблема источника), а не 500."""
    client, _ = client_with(telegram=FakeTelegram(fail_on={"download_file"}))
    media_id = _create_media_file()

    resp = client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 502


# ── вытеснение: лимит в ЗАЯВКАХ, а не в файлах ───────────────────────


def test_eviction_keeps_limit_in_requests_not_files(client_with, cache_dir, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "preview_cache_max_requests", 2)
    client, _ = client_with()

    # Три заявки, у первой ДВА фото: если бы лимит считался в файлах, она одна
    # вытеснила бы остальные.
    ids = {
        "250101-701": [_create_media_file(request_number="250101-701"),
                       _create_media_file(request_number="250101-701")],
        "250101-702": [_create_media_file(request_number="250101-702")],
        "250101-703": [_create_media_file(request_number="250101-703")],
    }
    for number, media_ids in ids.items():
        for mid in media_ids:
            r = client.get(f"/api/v1/media/{mid}/preview", headers={"X-API-Key": "testkey"})
            assert r.status_code == 200
            # mtime каталога — основа LRU; в тесте события идут в одну секунду,
            # поэтому разносим их явно.
            os.utime(os.path.join(cache_dir, number),
                     (0, 1_700_000_000 + list(ids).index(number)))

    buckets = sorted(os.listdir(cache_dir))
    assert len(buckets) == 2, buckets
    assert "250101-701" not in buckets  # самая давняя вытеснена целиком
    assert buckets == ["250101-702", "250101-703"]


def test_cache_hit_refreshes_recency(client_with, cache_dir, monkeypatch):
    """LRU по ЧТЕНИЮ: заявку, которую продолжают смотреть, вытеснять нельзя."""
    from app.core.config import settings
    from app.services import preview_cache

    monkeypatch.setattr(settings, "preview_cache_max_requests", 2)
    client, _ = client_with()
    a = _create_media_file(request_number="250101-801")
    b = _create_media_file(request_number="250101-802")
    for mid in (a, b):
        client.get(f"/api/v1/media/{mid}/preview", headers={"X-API-Key": "testkey"})
    os.utime(os.path.join(cache_dir, "250101-801"), (0, 1_700_000_000))
    os.utime(os.path.join(cache_dir, "250101-802"), (0, 1_700_000_001))

    # Читаем «старую» — её давность обновляется...
    assert preview_cache.get(a, "250101-801") is not None
    # ...и при добавлении третьей вытесняется уже 802, а не 801.
    c = _create_media_file(request_number="250101-803")
    client.get(f"/api/v1/media/{c}/preview", headers={"X-API-Key": "testkey"})

    buckets = sorted(os.listdir(cache_dir))
    assert "250101-801" in buckets
    assert "250101-802" not in buckets


# ── корень инцидента: сессия БД и параллелизм ────────────────────────


def test_serving_endpoints_do_not_hold_db_session():
    """Регрессия инцидента: ни `/file`, ни `/preview` не берут сессию через
    Depends — FastAPI держал бы её всё время скачивания из Telegram, и пул
    5+10 выедался десятком одновременных картинок. Метаданные читаются
    короткой сессией внутри `_load_servable_media` и она закрывается ДО I/O."""
    from app.api.v1.media import get_media_file_stream, get_media_preview

    for fn in (get_media_file_stream, get_media_preview):
        params = inspect.signature(fn).parameters
        assert "db" not in params, f"{fn.__name__} снова держит сессию БД через Depends"


@pytest.mark.asyncio
async def test_download_semaphore_caps_concurrency():
    from app.core.config import settings
    from app.services import preview_cache

    sem = preview_cache.download_semaphore()
    active = peak = 0

    async def worker():
        nonlocal active, peak
        async with sem:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(worker() for _ in range(20)))

    assert peak <= settings.telegram_download_concurrency
    assert peak > 0


def test_telegram_download_goes_through_semaphore():
    """Семафор должен стоять в самом `download_file`, а не в вызывающих: иначе
    любой новый путь скачивания снова уйдёт в Telegram без ограничения."""
    from app.services.telegram_client import TelegramClientService

    src = inspect.getsource(TelegramClientService.download_file)
    assert "download_semaphore" in src


def test_maintenance_endpoint_reports_cache_state(client_with):
    """Ручка обслуживания — то, чем после деплоя проверяют потолок кэша."""
    client, _ = client_with()
    media_id = _create_media_file(request_number="250101-900")
    client.get(f"/api/v1/media/{media_id}/preview", headers={"X-API-Key": "testkey"})

    resp = client.get("/api/v1/media/maintenance/preview-cache", headers={"X-API-Key": "testkey"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requests_cached"] == 1
    assert body["files"] == 1
    assert body["bytes"] > 0
    assert body["limit_requests"] >= 1


# ── прогрев (POST /previews/warm) ─────────────────────────────────────


def test_warm_builds_previews_without_returning_bytes(client_with, cache_dir):
    """UK зовёт это сразу после публикации, чтобы житель не попал на холодный
    кэш. Байты наружу не отдаются — только счётчики."""
    client, svc = client_with()
    a = _create_media_file(request_number="250101-950")
    b = _create_media_file(request_number="250101-950")

    resp = client.post("/api/v1/media/previews/warm", json={"media_ids": [a, b]},
                       headers={"X-API-Key": "testkey"})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"warmed": 2, "already_cached": 0, "failed": 0}
    assert len(svc.telegram.download_file_calls) == 2
    assert sorted(os.listdir(os.path.join(cache_dir, "250101-950"))) == [f"{a}.jpg", f"{b}.jpg"]


def test_warm_is_idempotent_and_cheap_on_second_call(client_with):
    """Повторный прогрев не должен снова качать: тик планировщика зовёт ручку
    каждые 10 минут по последним 24 отчётам."""
    client, svc = client_with()
    media_id = _create_media_file(request_number="250101-951")

    first = client.post("/api/v1/media/previews/warm", json={"media_ids": [media_id]},
                        headers={"X-API-Key": "testkey"})
    second = client.post("/api/v1/media/previews/warm", json={"media_ids": [media_id]},
                         headers={"X-API-Key": "testkey"})

    assert first.json()["warmed"] == 1
    assert second.json() == {"warmed": 0, "already_cached": 1, "failed": 0}
    assert len(svc.telegram.download_file_calls) == 1


def test_warm_counts_failures_and_continues(client_with):
    """Сбойный/удалённый файл не срывает прогрев остальных."""
    client, _ = client_with()
    ok = _create_media_file(request_number="250101-952")
    gone = _create_media_file(request_number="250101-952", status="deleted")

    resp = client.post("/api/v1/media/previews/warm", json={"media_ids": [gone, ok, 999999]},
                       headers={"X-API-Key": "testkey"})

    body = resp.json()
    assert body["warmed"] == 1
    assert body["failed"] == 2


def test_warm_rejects_empty_and_oversized_batches(client_with):
    client, _ = client_with()

    assert client.post("/api/v1/media/previews/warm", json={"media_ids": []},
                       headers={"X-API-Key": "testkey"}).status_code == 422
    assert client.post("/api/v1/media/previews/warm", json={"media_ids": list(range(201))},
                       headers={"X-API-Key": "testkey"}).status_code == 422
