"""Интеграция access_control ↔ медиа-сервис (§11, §10.2): загрузка/отдача фото проезда.

Покрываем:
* тонкий клиент ``AccessMediaClient``: отсутствие ``MEDIA_*`` env → понятная
  ``MediaConfigError`` при использовании (не на импорте);
* эндпоинт загрузки фото (device-auth, ВНЕ пути решения §10.2):
  ``POST /edge/{controller_id}/camera-events/{event_id}/photos`` — для каждого
  присланного кадра зовёт медиа-клиент с ``kind``/``ref`` и пишет
  ``camera_events.{plate|overview}_photo_url = media://{id}``; идемпотентен;
  device-auth обязателен (401 без подписи); изоляция по controller_id (403);
* отдача ``/photos``: ``media://`` → стрим байтов из (замоканного) медиа-клиента
  + аудит ``access.photo_view``; сырой URL → прежний 302 redirect (совместимость);
* симулятор: синтетическая дослка фото на эндпоинт (сквозной путь).

Медиа-сервис НЕ поднимается: ``AccessMediaClient`` подменяется фейком через
``app.dependency_overrides`` (загрузка/отдача — не реальный HTTP). PostgreSQL-only
(сидинг через ``pg_db``/``pilot``), кроме unit-теста конфигурации клиента.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.integrations.media import (
    AccessMediaClient,
    MediaConfigError,
    get_access_media_client,
)
from access_control.services import photo_urls as pu
from access_control.tests.conftest import DEVICE_API_KEY, device_headers
from access_control.tests.test_operator_read_api import _seed_camera_event


# ------------------------------ фейковый медиа-клиент ------------------------------


class FakeMediaClient:
    """Замена ``AccessMediaClient`` в тестах: пишет вызовы, не делает HTTP."""

    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.fetched: list[int] = []
        self._next_id = 100
        self.stream_bytes = b"\xff\xd8\xffSYNTHETIC-JPEG"
        self.stream_content_type = "image/jpeg"

    async def upload_access_photo(
        self, kind, ref, file_data, filename, content_type="image/jpeg", uploaded_by=None
    ) -> dict:
        content = file_data.read() if hasattr(file_data, "read") else file_data
        mid = self._next_id
        self._next_id += 1
        self.uploads.append(
            {
                "kind": kind,
                "ref": ref,
                "filename": filename,
                "content_type": content_type,
                "size": len(content),
            }
        )
        return {
            "media_id": mid,
            "telegram_file_id": f"tg-{mid}",
            "file_url": f"/api/v1/media/{mid}/file",
        }

    async def fetch_file(self, media_id) -> tuple[bytes, str]:
        self.fetched.append(int(media_id))
        return self.stream_bytes, self.stream_content_type


def _app_with_media(fake: FakeMediaClient):
    app = create_app()
    app.dependency_overrides[get_access_media_client] = lambda: fake
    return app


# ------------------------------ device-auth multipart ------------------------------


def _signed_multipart_post(client, controller_uid, path, files, *, api_key=DEVICE_API_KEY):
    """POST multipart с валидной device-auth подписью тела (§9.1).

    Тело multipart строится один раз через ``httpx.Request`` (фиксированный boundary)
    и ровно эти байты подписываются и отправляются — HMAC body совпадает.
    """
    req = httpx.Request("POST", "http://testserver" + path, files=files)
    body = req.read()
    headers = device_headers(controller_uid, method="POST", path=path, body=body, api_key=api_key)
    headers["content-type"] = req.headers["content-type"]
    return client.post(path, content=body, headers=headers)


def _photos_path(controller_uid: str, event_id: str) -> str:
    return f"/api/v1/access/edge/{controller_uid}/camera-events/{event_id}/photos"


# ------------------------------ клиент: конфигурация ------------------------------


def test_media_client_missing_config_raises(monkeypatch) -> None:
    """Отсутствие MEDIA_* env → понятная MediaConfigError при использовании (не на импорте)."""
    monkeypatch.delenv("MEDIA_SERVICE_URL", raising=False)
    monkeypatch.delenv("MEDIA_API_KEY", raising=False)
    client = AccessMediaClient()
    with pytest.raises(MediaConfigError):
        asyncio.run(
            client.upload_access_photo(
                kind="plate", ref="c|e", file_data=b"x", filename="p.jpg"
            )
        )
    with pytest.raises(MediaConfigError):
        asyncio.run(client.fetch_file(1))


def test_media_client_rejects_unknown_kind() -> None:
    client = AccessMediaClient(base_url="http://media", api_key="k")
    with pytest.raises(ValueError):
        asyncio.run(
            client.upload_access_photo(
                kind="bogus", ref="c|e", file_data=b"x", filename="p.jpg"
            )
        )


# ------------------------------ эндпоинт загрузки ------------------------------


def test_photos_upload_route_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert (
        "/api/v1/access/edge/{controller_id}/camera-events/{event_id}/photos" in paths
    )


def test_upload_photos_stores_media_ref(pg_db, pilot) -> None:
    _seed_camera_event(pg_db, pilot, event_id="ev-photo", plate="01PH000")
    pg_db.commit()

    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    path = _photos_path(pilot.controller_uid, "ev-photo")
    resp = _signed_multipart_post(
        client,
        pilot.controller_uid,
        path,
        files={
            "plate": ("plate.jpg", b"PLATEBYTES", "image/jpeg"),
            "overview": ("ov.jpg", b"OVERVIEWBYTES", "image/jpeg"),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert set(body["updated"]) == {"plate", "overview"}

    # Медиа-клиент вызван с правильными kind/ref.
    kinds = {u["kind"]: u for u in fake.uploads}
    assert set(kinds) == {"plate", "overview"}
    expected_ref = f"{pilot.controller_uid}|ev-photo"
    assert all(u["ref"] == expected_ref for u in fake.uploads)

    # camera_events.*_photo_url стали media://{id}.
    row = pg_db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": pilot.controller_id, "e": "ev-photo"},
    ).mappings().first()
    assert row["plate_photo_url"].startswith("media://")
    assert row["overview_photo_url"].startswith("media://")


def test_upload_single_kind_only(pg_db, pilot) -> None:
    _seed_camera_event(pg_db, pilot, event_id="ev-one", plate="01ONE00")
    pg_db.commit()
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    resp = _signed_multipart_post(
        client,
        pilot.controller_uid,
        _photos_path(pilot.controller_uid, "ev-one"),
        files={"plate": ("plate.jpg", b"ONLYPLATE", "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == ["plate"]
    assert len(fake.uploads) == 1
    row = pg_db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": pilot.controller_id, "e": "ev-one"},
    ).mappings().first()
    assert row["plate_photo_url"].startswith("media://")
    assert row["overview_photo_url"] is None


def test_upload_idempotent_overwrites_same_kind(pg_db, pilot) -> None:
    _seed_camera_event(pg_db, pilot, event_id="ev-idem", plate="01IDM00")
    pg_db.commit()
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    path = _photos_path(pilot.controller_uid, "ev-idem")

    r1 = _signed_multipart_post(
        client, pilot.controller_uid, path,
        files={"plate": ("p.jpg", b"FIRST", "image/jpeg")},
    )
    first_ref = pg_db.execute(
        text("SELECT plate_photo_url FROM camera_events WHERE event_id = 'ev-idem'")
    ).scalar_one()
    r2 = _signed_multipart_post(
        client, pilot.controller_uid, path,
        files={"plate": ("p.jpg", b"SECOND", "image/jpeg")},
    )
    second_ref = pg_db.execute(
        text("SELECT plate_photo_url FROM camera_events WHERE event_id = 'ev-idem'")
    ).scalar_one()
    assert r1.status_code == 200 and r2.status_code == 200
    assert first_ref.startswith("media://") and second_ref.startswith("media://")
    assert first_ref != second_ref  # перезаписался ref того же kind


def test_upload_requires_device_auth(pg_db, pilot) -> None:
    _seed_camera_event(pg_db, pilot, event_id="ev-noauth", plate="01NA000")
    pg_db.commit()
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    path = _photos_path(pilot.controller_uid, "ev-noauth")
    # Без device-auth заголовков → 401.
    resp = client.post(path, files={"plate": ("p.jpg", b"X", "image/jpeg")})
    assert resp.status_code == 401
    assert fake.uploads == []


def test_upload_controller_isolation(pg_db, pilot, pilot_b) -> None:
    """Контроллер B не может слать фото на путь контроллера A (§9.1) → 403."""
    _seed_camera_event(pg_db, pilot, event_id="ev-iso", plate="01ISO00")
    pg_db.commit()
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    # Путь контроллера A, но подписываем как B → path mismatch 403.
    path = _photos_path(pilot.controller_uid, "ev-iso")
    resp = _signed_multipart_post(
        client, pilot_b.controller_uid, path,
        files={"plate": ("p.jpg", b"X", "image/jpeg")},
    )
    assert resp.status_code == 403
    assert fake.uploads == []


# ------------------------------ отдача /photos ------------------------------


def _audit_count(db, action: str = "access.photo_view") -> int:
    return db.execute(
        text("SELECT count(*) FROM access_audit_logs WHERE action = :a"),
        {"a": action},
    ).scalar_one()


def test_photos_media_ref_streams_bytes_and_audits(pg_db, pilot) -> None:
    ce = _seed_camera_event(
        pg_db, pilot, event_id="ev-stream", plate="01STR00",
        plate_photo_url="media://555",
    )
    pg_db.commit()
    before = _audit_count(pg_db)

    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    url = pu.sign(ce, "plate", ttl_seconds=300)
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert resp.content == fake.stream_bytes
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert fake.fetched == [555]

    pg_db.commit()
    assert _audit_count(pg_db) == before + 1


def test_photos_raw_url_still_redirects(pg_db, pilot) -> None:
    """Обратная совместимость: сырой storage-URL → прежний 302 redirect, медиа не дёргаем."""
    ce = _seed_camera_event(
        pg_db, pilot, event_id="ev-raw", plate="01RAW00",
        plate_photo_url="https://cdn.example/plate/raw.jpg",
    )
    pg_db.commit()
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    url = pu.sign(ce, "plate", ttl_seconds=300)
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://cdn.example/plate/raw.jpg"
    assert fake.fetched == []  # медиа-сервис не вызывался для сырого URL


# ------------------------------ симулятор (сквозной путь) ------------------------------


def test_simulator_can_send_synthetic_photos(pg_db, pilot) -> None:
    from access_control.edge.anpr_simulator import AnprSimulator

    _seed_camera_event(pg_db, pilot, event_id="ev-sim", plate="01SIM00")
    pg_db.commit()
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    sim = AnprSimulator(
        client,
        controller_uid=pilot.controller_uid,
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        barrier_id=pilot.barrier_id,
    )
    resp = sim.send_photos(
        event_id="ev-sim", plate_bytes=b"SIMPLATE", overview_bytes=b"SIMOVER"
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["updated"]) == {"plate", "overview"}
    assert len(fake.uploads) == 2
