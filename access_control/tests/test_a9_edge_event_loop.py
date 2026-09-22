"""A9-P2-13 / A9-P2-14 / A9-P3-12: event loop, транзакции и long-poll access-api.

* P2-13: ``authenticate_edge`` (7 edge-ручек) и ``get_photo`` — async, но гоняли
  синхронный SQL прямо в event loop однопроцессного сервиса (``--workers 1``).
  Теперь SQL уходит в threadpool. Ошибка медиа-сервиса на ``/photos`` больше не
  500 при уже закоммиченном аудите: 404 от media → 404, прочее → 502, аудит
  просмотра пишется только после успешного получения байтов.
* P2-14: загрузка кадров шла под открытой транзакцией и row-lock ``camera_events``
  (UPDATE plate → загрузка overview до 30 с); при 404 события кадр уже загружен
  и осиротел. Теперь: короткая проверка события → загрузка обоих кадров → одна
  короткая транзакция записи ссылок; при сбое загруженное удаляется best-effort.
* P3-12: long-poll ``commands/next`` спал ``time.sleep`` в sync-эндпоинте — поток
  anyio занят до 25 с. Теперь async-эндпоинт + ``asyncio.sleep``.

PostgreSQL-only (``pg_db``/``pilot``).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from access_control.api import commands
from access_control.api import registry
from access_control.app.main import create_app
from access_control.services import device_auth
from access_control.services import photo_urls as pu
from access_control.tests.conftest import (
    SigningClient,
    device_headers,
    seed_barrier_command,
)
from access_control.tests.test_access_media import (
    FakeMediaClient,
    _app_with_media,
    _photos_path,
    _signed_multipart_post,
)
from access_control.tests.test_operator_read_api import _seed_camera_event


def _in_event_loop() -> bool:
    """True, если код исполняется в потоке с работающим event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "http://media/api/v1/media/1/file")
    return httpx.HTTPStatusError(
        f"media {code}", request=req, response=httpx.Response(code, request=req)
    )


def _audit_count(db) -> int:
    return db.execute(
        text("SELECT count(*) FROM access_audit_logs WHERE action = 'access.photo_view'")
    ).scalar_one()


def _photo_refs(db, pilot, event_id: str):
    return db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": pilot.controller_id, "e": event_id},
    ).mappings().first()


# ------------------------------ A9-P2-13: device-auth ------------------------------


def test_authenticate_edge_runs_sql_off_event_loop(pg_db, pilot, monkeypatch) -> None:
    """Синхронная проверка device-auth (SQL) не исполняется в event loop."""
    seen: list[bool] = []
    original = device_auth.authenticate

    def _spy(*args, **kwargs):
        seen.append(_in_event_loop())
        return original(*args, **kwargs)

    monkeypatch.setattr(device_auth, "authenticate", _spy)
    client = SigningClient(TestClient(create_app()), pilot.controller_uid)
    resp = client.get(f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot")
    assert resp.status_code == 200
    assert seen == [False]


# ------------------------------ A9-P2-13: /photos ------------------------------


def _signed_photo_url(pg_db, pilot, event_id: str) -> str:
    ce = _seed_camera_event(
        pg_db, pilot, event_id=event_id, plate="01PH000", plate_photo_url="media://777"
    )
    pg_db.commit()
    return pu.sign(ce, "plate", ttl_seconds=300)


class _FailingFetchMedia(FakeMediaClient):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    async def fetch_file(self, media_id):
        self.fetched.append(int(media_id))
        raise self._exc


def test_photo_media_404_maps_to_404_without_audit(pg_db, pilot) -> None:
    url = _signed_photo_url(pg_db, pilot, "ev-m404")
    before = _audit_count(pg_db)
    client = TestClient(_app_with_media(_FailingFetchMedia(_status_error(404))))
    resp = client.get(url)
    assert resp.status_code == 404
    pg_db.commit()
    assert _audit_count(pg_db) == before  # просмотра не было


def test_photo_media_5xx_maps_to_502_without_audit(pg_db, pilot) -> None:
    url = _signed_photo_url(pg_db, pilot, "ev-m500")
    before = _audit_count(pg_db)
    client = TestClient(_app_with_media(_FailingFetchMedia(_status_error(500))))
    resp = client.get(url)
    assert resp.status_code == 502
    pg_db.commit()
    assert _audit_count(pg_db) == before


def test_photo_media_network_error_maps_to_502(pg_db, pilot) -> None:
    url = _signed_photo_url(pg_db, pilot, "ev-mnet")
    exc = httpx.ConnectError("refused", request=httpx.Request("GET", "http://media"))
    client = TestClient(_app_with_media(_FailingFetchMedia(exc)))
    assert client.get(url).status_code == 502


def test_photo_sql_and_audit_run_off_event_loop(pg_db, pilot, monkeypatch) -> None:
    url = _signed_photo_url(pg_db, pilot, "ev-offloop")
    seen: list[bool] = []
    original = registry.write_audit

    def _spy(*args, **kwargs):
        seen.append(_in_event_loop())
        return original(*args, **kwargs)

    monkeypatch.setattr(registry, "write_audit", _spy)
    client = TestClient(_app_with_media(FakeMediaClient()))
    assert client.get(url).status_code == 200
    assert seen == [False]


# ------------------------------ A9-P2-14: фото проезда ------------------------------


def test_unknown_event_404_without_upload(pg_db, pilot) -> None:
    """Событие неизвестно → 404 ДО загрузки: осиротевших медиа нет."""
    fake = FakeMediaClient()
    client = TestClient(_app_with_media(fake))
    resp = _signed_multipart_post(
        client,
        pilot.controller_uid,
        _photos_path(pilot.controller_uid, "ev-missing"),
        files={
            "plate": ("p.jpg", b"P", "image/jpeg"),
            "overview": ("o.jpg", b"O", "image/jpeg"),
        },
    )
    assert resp.status_code == 404
    assert fake.uploads == []


class _LockProbeMedia(FakeMediaClient):
    """На каждой загрузке пробует взять row-lock события из ЧУЖОЙ сессии."""

    def __init__(self, probe_db, event_id: str) -> None:
        super().__init__()
        self._db = probe_db
        self._event_id = event_id
        self.row_locked: list[bool] = []

    async def upload_access_photo(self, kind, ref, file_data, filename, **kw):
        try:
            self._db.execute(
                text(
                    "SELECT id FROM camera_events WHERE event_id = :e "
                    "FOR UPDATE NOWAIT"
                ),
                {"e": self._event_id},
            ).first()
            self.row_locked.append(False)
        except OperationalError:
            self.row_locked.append(True)
        finally:
            self._db.rollback()
        return await super().upload_access_photo(kind, ref, file_data, filename, **kw)


def test_uploads_happen_without_row_lock(pg_db, pilot) -> None:
    """Во время загрузки кадров строка camera_events не залочена запросом."""
    _seed_camera_event(pg_db, pilot, event_id="ev-lock", plate="01LK000")
    pg_db.commit()
    fake = _LockProbeMedia(pg_db, "ev-lock")
    client = TestClient(_app_with_media(fake))
    resp = _signed_multipart_post(
        client,
        pilot.controller_uid,
        _photos_path(pilot.controller_uid, "ev-lock"),
        files={
            "plate": ("p.jpg", b"P", "image/jpeg"),
            "overview": ("o.jpg", b"O", "image/jpeg"),
        },
    )
    assert resp.status_code == 200, resp.text
    assert fake.row_locked == [False, False]
    refs = _photo_refs(pg_db, pilot, "ev-lock")
    assert refs["plate_photo_url"] == "media://100"
    assert refs["overview_photo_url"] == "media://101"


class _FailSecondUploadMedia(FakeMediaClient):
    async def upload_access_photo(self, kind, ref, file_data, filename, **kw):
        if kind == "overview":
            raise _status_error(503)
        return await super().upload_access_photo(kind, ref, file_data, filename, **kw)


def test_failed_second_upload_deletes_first_and_keeps_refs(pg_db, pilot) -> None:
    """Сбой загрузки overview → plate удаляется из media, ссылки не записаны, 502."""
    _seed_camera_event(pg_db, pilot, event_id="ev-fail2", plate="01FL000")
    pg_db.commit()
    fake = _FailSecondUploadMedia()
    client = TestClient(_app_with_media(fake))
    resp = _signed_multipart_post(
        client,
        pilot.controller_uid,
        _photos_path(pilot.controller_uid, "ev-fail2"),
        files={
            "plate": ("p.jpg", b"P", "image/jpeg"),
            "overview": ("o.jpg", b"O", "image/jpeg"),
        },
    )
    assert resp.status_code == 502
    assert fake.deleted == [100]
    refs = _photo_refs(pg_db, pilot, "ev-fail2")
    assert refs["plate_photo_url"] is None
    assert refs["overview_photo_url"] is None


class _DeleteEventDuringUploadMedia(FakeMediaClient):
    """Событие исчезает между проверкой и записью (гонка с чисткой)."""

    def __init__(self, probe_db, event_id: str) -> None:
        super().__init__()
        self._db = probe_db
        self._event_id = event_id

    async def upload_access_photo(self, kind, ref, file_data, filename, **kw):
        self._db.execute(
            text("DELETE FROM camera_events WHERE event_id = :e"), {"e": self._event_id}
        )
        self._db.commit()
        return await super().upload_access_photo(kind, ref, file_data, filename, **kw)


def test_event_vanished_before_write_404_and_cleanup(pg_db, pilot) -> None:
    _seed_camera_event(pg_db, pilot, event_id="ev-gone", plate="01GN000")
    pg_db.commit()
    fake = _DeleteEventDuringUploadMedia(pg_db, "ev-gone")
    client = TestClient(_app_with_media(fake))
    resp = _signed_multipart_post(
        client,
        pilot.controller_uid,
        _photos_path(pilot.controller_uid, "ev-gone"),
        files={"plate": ("p.jpg", b"P", "image/jpeg")},
    )
    assert resp.status_code == 404
    assert fake.deleted == [100]


# ------------------------------ A9-P3-12: long-poll ------------------------------


def test_next_command_endpoint_is_async() -> None:
    assert inspect.iscoroutinefunction(commands.get_next_command)


async def test_long_poll_frees_event_loop_and_picks_up_command(
    pg_db, pilot, _pg_sessionmaker
) -> None:
    """Во время ожидания loop свободен: команда, поставленная позже, выдаётся."""
    lease_db = _pg_sessionmaker()

    async def _enqueue_later() -> str:
        await asyncio.sleep(0.3)
        return seed_barrier_command(pg_db, pilot)

    try:
        enqueue = asyncio.create_task(_enqueue_later())
        leased = await commands.lease_next_command_async(
            lease_db, pilot.controller_id, long_poll_seconds=3.0
        )
        command_id = await enqueue
    finally:
        lease_db.close()
    assert leased is not None
    assert leased.command_id == command_id


def test_long_poll_endpoint_empty_queue_204(pg_db, pilot) -> None:
    client = SigningClient(TestClient(create_app()), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next?wait=0.3"
    )
    assert resp.status_code == 204


# ---------------- ревью A9-P3-12: соединение БД на время long-poll ----------------


def test_long_poll_attempts_start_without_open_transaction(
    pg_db, pilot, monkeypatch
) -> None:
    """После device-auth транзакция закрыта: long-poll не держит соединение."""
    seen: list[bool] = []
    original = commands._try_lease

    def _spy(db, *args, **kwargs):
        seen.append(db.in_transaction())
        return original(db, *args, **kwargs)

    monkeypatch.setattr(commands, "_try_lease", _spy)
    client = SigningClient(TestClient(create_app()), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next?wait=0.6"
    )
    assert resp.status_code == 204
    assert len(seen) >= 2
    assert not any(seen)


# Больше, чем пул (10+10) + потоки anyio (40): раньше 20 висящих «idle in
# transaction» соединений + 40 потоков, ждущих pool_timeout, вешали /health.
PARALLEL_POLLS = 70


async def test_parallel_long_polls_do_not_exhaust_pool_or_block_health(
    pg_db, pilot
) -> None:
    """Параллельных long-poll больше пула и потоков — пул свободен, /health жив."""
    app = create_app()
    path = f"/api/v1/access/edge/{pilot.controller_uid}/commands/next"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:

        async def _poll() -> int:
            headers = device_headers(pilot.controller_uid, method="GET", path=path)
            resp = await ac.get(path, params={"wait": 1.5}, headers=headers)
            return resp.status_code

        polls = [asyncio.create_task(_poll()) for _ in range(PARALLEL_POLLS)]
        await asyncio.sleep(0.7)
        loop = asyncio.get_running_loop()
        started = loop.time()
        health = await ac.get("/health")
        health_seconds = loop.time() - started
        codes = await asyncio.gather(*polls)

    assert health.status_code == 200
    assert health_seconds < 2.0
    # Ни один long-poll не упал в pool_timeout: соединение берётся только на
    # время SQL-попытки, между попытками и после auth оно возвращено в пул.
    assert codes == [204] * PARALLEL_POLLS


# ---------------- ревью A9-P3-12: обрыв клиента и возврат лизы ----------------


async def test_long_poll_stops_when_client_disconnected(
    pg_db, pilot, _pg_sessionmaker
) -> None:
    """Клиент ушёл — команду мёртвому клиенту не лизим, она остаётся pending."""
    lease_db = _pg_sessionmaker()
    polls = 0

    async def _disconnected() -> bool:
        nonlocal polls
        polls += 1
        if polls == 2:
            seed_barrier_command(pg_db, pilot)  # появилась ПОСЛЕ обрыва
        return polls >= 2

    try:
        leased = await commands.lease_next_command_async(
            lease_db, pilot.controller_id, long_poll_seconds=3.0,
            is_disconnected=_disconnected,
        )
    finally:
        lease_db.close()
    assert leased is None
    pending = pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE status = 'pending'")
    ).scalar()
    assert pending == 1


@pytest.fixture()
def reclaim_on(monkeypatch):
    monkeypatch.setenv(commands.RECLAIM_ENV, "true")


def test_reclaim_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv(commands.RECLAIM_ENV, raising=False)
    assert commands.reclaim_enabled() is False


def _expired_lease(pg_db, pilot, *, attempts: int = 1, max_attempts: int = 5) -> str:
    return seed_barrier_command(
        pg_db, pilot, status="leased", attempts=attempts, max_attempts=max_attempts,
        lease_token=commands.hash_lease_token("old-token"),
        lease_expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5),
    )


def test_expired_lease_not_reissued_when_reclaim_off(pg_db, pilot, monkeypatch) -> None:
    """Флаг выключен — прежнее fail-safe поведение: истёкшая лиза не переиздаётся."""
    monkeypatch.setenv(commands.RECLAIM_ENV, "false")
    _expired_lease(pg_db, pilot)
    assert commands.lease_next_command(pg_db, pilot.controller_id) is None


def test_expired_lease_is_reclaimed_and_old_token_rejected(
    pg_db, pilot, reclaim_on
) -> None:
    cmd = _expired_lease(pg_db, pilot)
    leased = commands.lease_next_command(pg_db, pilot.controller_id)
    assert leased is not None and leased.command_id == cmd
    assert leased.lease_token != "old-token"
    # Старый держатель (оборванный клиент) не может заакать — CAS по новому токену.
    with pytest.raises(commands.AckConflict):
        commands.ack_command(pg_db, pilot.controller_id, cmd, "old-token", {"ok": True})
    outcome = commands.ack_command(
        pg_db, pilot.controller_id, cmd, leased.lease_token, {"ok": True}
    )
    assert outcome.status == "acked"


def test_live_lease_is_not_reissued(pg_db, pilot, reclaim_on) -> None:
    seed_barrier_command(
        pg_db, pilot, status="leased", attempts=1,
        lease_token=commands.hash_lease_token("live"),
        lease_expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30),
    )
    assert commands.lease_next_command(pg_db, pilot.controller_id) is None


def test_expired_lease_over_max_attempts_not_reclaimed(
    pg_db, pilot, reclaim_on
) -> None:
    _expired_lease(pg_db, pilot, attempts=5, max_attempts=5)
    assert commands.lease_next_command(pg_db, pilot.controller_id) is None
