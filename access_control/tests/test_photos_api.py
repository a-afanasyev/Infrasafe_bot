"""Эндпоинт выдачи фото по signed-URL (§11): capability + аудит просмотра.

``GET /api/v1/access/photos/{kind}/{event_id}?exp=&sig=`` — capability по
короткоживущему signed-URL (для ``<img src>``, который не может слать
Authorization). Bearer/cookie НЕ требуется; короткий TTL компенсирует.

Покрываем:
* валидный sig → 302 redirect на сохранённый storage-URL + запись аудита
  ``access.photo_view`` в ``access_audit_logs`` (PD-safe details, без номера);
* протухший sig → 410, аудита просмотра нет;
* подделанный sig → 403, аудита просмотра нет;
* пустой *_photo_url при валидном sig → 404;
* registry list/detail отдают подписанные URL (sig+exp, путь /photos/...),
  по которым реально открывается фото (round-trip).

PostgreSQL-only (сидинг через ``pg_db``/``pilot``).
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services import photo_urls as pu
from access_control.tests.conftest import seed_user
from access_control.tests.test_operator_read_api import _client, _seed_camera_event


def _audit_count(db, action: str = "access.photo_view") -> int:
    return db.execute(
        text("SELECT count(*) FROM access_audit_logs WHERE action = :a"),
        {"a": action},
    ).scalar_one()


def test_photos_route_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/access/photos/{kind}/{event_id}" in paths


def test_valid_signed_url_redirects_and_audits(pg_db, pilot) -> None:
    ce = _seed_camera_event(
        pg_db,
        pilot,
        event_id="ev-ok",
        plate="01OK000",
        plate_photo_url="https://cdn.example/plate/ev-ok.jpg",
    )
    pg_db.commit()
    before = _audit_count(pg_db)

    url = pu.sign(ce, "plate", ttl_seconds=300)
    # Без auth: capability по signed-URL.
    client = TestClient(create_app())
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://cdn.example/plate/ev-ok.jpg"

    pg_db.commit()  # увидеть запись, сделанную в сессии запроса
    assert _audit_count(pg_db) == before + 1
    row = pg_db.execute(
        text(
            "SELECT action, entity_type, entity_id, details FROM access_audit_logs "
            "WHERE action = 'access.photo_view' ORDER BY id DESC LIMIT 1"
        )
    ).mappings().first()
    assert row["entity_type"] == "camera_event"
    assert row["entity_id"] == str(ce)
    # PD-safe: ни номера, ни storage-URL в details.
    details = row["details"] or {}
    assert "01OK000" not in str(details)
    assert "cdn.example" not in str(details)
    assert details.get("kind") == "plate"


def test_expired_signed_url_410_no_audit(pg_db, pilot) -> None:
    ce = _seed_camera_event(
        pg_db, pilot, event_id="ev-exp", plate="01EXP00",
        plate_photo_url="https://cdn.example/plate/ev-exp.jpg",
    )
    pg_db.commit()
    before = _audit_count(pg_db)

    past = int(time.time()) - 1
    sig = pu.compute_sig(ce, "plate", past)
    url = f"/api/v1/access/photos/plate/{ce}?exp={past}&sig={sig}"
    client = TestClient(create_app())
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 410
    pg_db.commit()
    assert _audit_count(pg_db) == before


def test_tampered_signed_url_403_no_audit(pg_db, pilot) -> None:
    ce = _seed_camera_event(
        pg_db, pilot, event_id="ev-tmp", plate="01TMP00",
        plate_photo_url="https://cdn.example/plate/ev-tmp.jpg",
    )
    pg_db.commit()
    before = _audit_count(pg_db)

    exp = int(time.time()) + 300
    bad = pu.compute_sig(ce, "plate", exp) + "ff"
    url = f"/api/v1/access/photos/plate/{ce}?exp={exp}&sig={bad}"
    client = TestClient(create_app())
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 403
    pg_db.commit()
    assert _audit_count(pg_db) == before


def test_valid_sig_but_empty_photo_404(pg_db, pilot) -> None:
    ce = _seed_camera_event(pg_db, pilot, event_id="ev-empty", plate="01EMP00")
    pg_db.commit()
    url = pu.sign(ce, "overview", ttl_seconds=300)
    client = TestClient(create_app())
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 404


def test_unknown_event_404(pg_db, pilot) -> None:
    url = pu.sign(999999, "plate", ttl_seconds=300)
    client = TestClient(create_app())
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 404


def test_registry_list_returns_signed_urls_for_photo_viewer(pg_db, pilot) -> None:
    """§11: список отдаёт подписанные URL (не сырой storage-URL) для роли с photo-view."""
    uid = seed_user(pg_db, roles="security_operator")
    _seed_camera_event(
        pg_db, pilot, event_id="ev-sgn", plate="01SGN00",
        plate_photo_url="https://cdn.example/plate/secret.jpg",
        overview_photo_url="https://cdn.example/overview/secret.jpg",
    )
    pg_db.commit()
    client = _client(uid, "security_operator")
    row = client.get("/api/v1/access/events?plate=01SGN00").json()["items"][0]
    for field in ("plate_photo_url", "overview_photo_url"):
        assert row[field] is not None
        assert row[field].startswith("/api/v1/access/photos/")
        assert "sig=" in row[field] and "exp=" in row[field]
        # сырой storage-URL наружу не отдаётся
        assert "cdn.example" not in row[field]


def test_registry_signed_url_roundtrip_opens_photo(pg_db, pilot) -> None:
    """URL из списка реально открывает фото (302 на сохранённый storage-URL)."""
    uid = seed_user(pg_db, roles="manager")
    _seed_camera_event(
        pg_db, pilot, event_id="ev-rt", plate="01RT000",
        plate_photo_url="https://cdn.example/plate/rt.jpg",
    )
    pg_db.commit()
    client = _client(uid, "manager")
    signed = client.get("/api/v1/access/events?plate=01RT000").json()[
        "items"
    ][0]["plate_photo_url"]
    # тем же app (без auth на /photos) идём по подписанному URL
    resp = client.get(signed, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://cdn.example/plate/rt.jpg"


def test_registry_detail_returns_signed_urls(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    ce = _seed_camera_event(
        pg_db, pilot, event_id="ev-d-sgn", plate="01DSG00",
        plate_photo_url="https://cdn.example/plate/d.jpg",
        overview_photo_url="https://cdn.example/overview/d.jpg",
    )
    pg_db.commit()
    client = _client(uid, "manager")
    cam = client.get(f"/api/v1/access/events/{ce}").json()["camera_event"]
    assert cam["plate_photo_url"].startswith("/api/v1/access/photos/plate/")
    assert cam["overview_photo_url"].startswith("/api/v1/access/photos/overview/")
    assert "cdn.example" not in cam["plate_photo_url"]


def test_can_view_photos_predicate() -> None:
    """Гейтинг photo-view (§11): только security_operator/manager/system_admin."""
    import types

    from access_control.api.registry import can_view_photos

    def u(role):
        return types.SimpleNamespace(roles=f'["{role}"]', active_role=role)

    assert can_view_photos(u("security_operator")) is True
    assert can_view_photos(u("manager")) is True
    assert can_view_photos(u("system_admin")) is True
    assert can_view_photos(u("applicant")) is False
    assert can_view_photos(u("executor")) is False
    assert can_view_photos(u("inspector")) is False
