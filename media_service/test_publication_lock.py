"""Тесты «publication lock» механизма media_service (T4).

Покрытие:
  - GET /{media_id}/file: предикат публичной отдачи байтов
    (active всегда; archived только с publication_locked=true;
    deleted/archiving/deleting — всегда 404).
  - acquire_publication_lock / release_publication_lock: атомарность,
    идемпотентность.
  - archive_media/delete_media: двухфазная сага, PublicationReservationError
    (409 на уровне endpoint), компенсация при сбое Telegram I/O.
  - list_publication_locks + GET /api/v1/media/publication-locks
    (проверка порядка регистрации маршрутов — не должен быть перехвачен
    bare /{media_id}).

Telegram мокается (access_test_utils.FakeTelegram) — реальные каналы/сеть
не нужны (см. conftest.py).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from access_test_utils import FakeTelegram

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------- helpers ----------

def _make_service(fail_on=None):
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram(fail_on=fail_on)
    svc.channels_cache = {}
    return svc


def _create_media_file(**overrides) -> int:
    """Вставляет строку MediaFile напрямую (минуя upload-флоу) для тестов."""
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    defaults = dict(
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


def _create_archive_channel() -> int:
    from app.db.database import SessionLocal
    from app.models.media import MediaChannel

    s = SessionLocal()
    try:
        existing = s.query(MediaChannel).filter(MediaChannel.purpose == "archive").first()
        if existing:
            return existing.id
        ch = MediaChannel(
            channel_name="uk_media_archive_test",
            channel_id=-1009999999999,
            channel_username="@archive_test",
            purpose="archive",
            category="mixed",
            is_active=True,
        )
        s.add(ch)
        s.commit()
        s.refresh(ch)
        return ch.id
    finally:
        s.close()


def _get_status_and_lock(media_id: int):
    from app.db.database import SessionLocal
    from app.models.media import MediaFile

    s = SessionLocal()
    try:
        mf = s.query(MediaFile).filter(MediaFile.id == media_id).first()
        if mf is None:
            return None, None
        return mf.status, mf.publication_locked
    finally:
        s.close()


@pytest.fixture
def client_and_service(monkeypatch):
    from app.main import app
    from app.api.v1.media import get_storage_service
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.telegram = FakeTelegram()
    svc.channels_cache = {}
    app.dependency_overrides[get_storage_service] = lambda: svc
    try:
        with TestClient(app) as c:
            yield c, svc
    finally:
        app.dependency_overrides.clear()


# ---------- GET /{media_id}/file predicate ----------

def test_file_stream_active_unlocked_returns_200(client_and_service):
    """Regression: самый частый случай (private-фото заявок/карточек) не должен ломаться."""
    client, _ = client_and_service
    media_id = _create_media_file(status="active", publication_locked=False)

    resp = client.get(f"/api/v1/media/{media_id}/file", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 200, resp.text


def test_file_stream_archived_and_locked_returns_200(client_and_service):
    client, _ = client_and_service
    media_id = _create_media_file(status="archived", publication_locked=True)

    resp = client.get(f"/api/v1/media/{media_id}/file", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("status_value", ["deleted", "archiving", "deleting"])
def test_file_stream_non_servable_statuses_return_404(client_and_service, status_value):
    client, _ = client_and_service
    media_id = _create_media_file(status=status_value, publication_locked=False)

    resp = client.get(f"/api/v1/media/{media_id}/file", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 404, resp.text


def test_file_stream_archived_without_lock_returns_404(client_and_service):
    """archived без publication_locked НЕ должен отдаваться публично."""
    client, _ = client_and_service
    media_id = _create_media_file(status="archived", publication_locked=False)

    resp = client.get(f"/api/v1/media/{media_id}/file", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 404, resp.text


# ---------- acquire/release publication lock (service level) ----------

@pytest.mark.asyncio
async def test_acquire_lock_on_active_file_succeeds_and_persists():
    svc = _make_service()
    media_id = _create_media_file(status="active")

    result = await svc.acquire_publication_lock(media_id)
    assert result is True

    status, locked = _get_status_and_lock(media_id)
    assert status == "active"
    assert locked is True


@pytest.mark.asyncio
async def test_acquire_lock_is_idempotent_on_already_locked_active_file():
    svc = _make_service()
    media_id = _create_media_file(status="active", publication_locked=True)

    result = await svc.acquire_publication_lock(media_id)
    assert result is True

    _, locked = _get_status_and_lock(media_id)
    assert locked is True


@pytest.mark.parametrize("status_value", ["archived", "deleted", "archiving", "deleting"])
@pytest.mark.asyncio
async def test_acquire_lock_fails_on_non_active_file(status_value):
    svc = _make_service()
    media_id = _create_media_file(status=status_value)

    result = await svc.acquire_publication_lock(media_id)
    assert result is False


@pytest.mark.asyncio
async def test_acquire_lock_fails_on_nonexistent_file():
    svc = _make_service()
    result = await svc.acquire_publication_lock(999_999)
    assert result is False


@pytest.mark.asyncio
async def test_release_lock_is_idempotent_never_locked():
    svc = _make_service()
    media_id = _create_media_file(status="active", publication_locked=False)

    await svc.release_publication_lock(media_id)  # should not raise

    _, locked = _get_status_and_lock(media_id)
    assert locked is False


@pytest.mark.asyncio
async def test_release_lock_actually_unlocks():
    svc = _make_service()
    media_id = _create_media_file(status="archived", publication_locked=True)

    await svc.release_publication_lock(media_id)

    _, locked = _get_status_and_lock(media_id)
    assert locked is False


@pytest.mark.asyncio
async def test_release_lock_on_missing_id_does_not_raise():
    svc = _make_service()
    await svc.release_publication_lock(999_999)  # no error


# ---------- archive_media / delete_media: reservation conflicts ----------

@pytest.mark.asyncio
async def test_archive_media_raises_on_publication_locked_active_file():
    from app.services.media_storage import PublicationReservationError

    svc = _make_service()
    _create_archive_channel()
    media_id = _create_media_file(status="active", publication_locked=True)

    with pytest.raises(PublicationReservationError):
        await svc.archive_media(media_id)

    # ничего не отправлено в Telegram — резервирование не прошло раньше I/O
    assert svc.telegram.get_file_url_calls == []
    status, locked = _get_status_and_lock(media_id)
    assert status == "active"
    assert locked is True


@pytest.mark.asyncio
async def test_delete_media_raises_on_publication_locked_active_file():
    from app.services.media_storage import PublicationReservationError

    svc = _make_service()
    media_id = _create_media_file(status="active", publication_locked=True)

    with pytest.raises(PublicationReservationError):
        await svc.delete_media(media_id)

    assert svc.telegram.delete_message_calls == []
    status, locked = _get_status_and_lock(media_id)
    assert status == "active"
    assert locked is True


@pytest.mark.asyncio
async def test_archive_media_raises_on_already_archived_file():
    from app.services.media_storage import PublicationReservationError

    svc = _make_service()
    media_id = _create_media_file(status="archived")

    with pytest.raises(PublicationReservationError):
        await svc.archive_media(media_id)


@pytest.mark.asyncio
async def test_archive_media_on_nonexistent_id_returns_false_not_exception():
    svc = _make_service()
    result = await svc.archive_media(999_999)
    assert result is False


@pytest.mark.asyncio
async def test_delete_media_on_nonexistent_id_returns_false_not_exception():
    svc = _make_service()
    result = await svc.delete_media(999_999)
    assert result is False


# ---------- endpoint-level: 409 mapping ----------

def test_archive_endpoint_returns_409_on_publication_locked(client_and_service):
    client, _ = client_and_service
    _create_archive_channel()
    media_id = _create_media_file(status="active", publication_locked=True)

    resp = client.post(
        f"/api/v1/media/{media_id}/archive",
        headers={"X-API-Key": "testkey"},
        json={},
    )
    assert resp.status_code == 409, resp.text


def test_delete_endpoint_returns_409_on_publication_locked(client_and_service):
    client, _ = client_and_service
    media_id = _create_media_file(status="active", publication_locked=True)

    resp = client.delete(
        f"/api/v1/media/{media_id}",
        headers={"X-API-Key": "testkey"},
    )
    assert resp.status_code == 409, resp.text


def test_archive_endpoint_returns_404_on_nonexistent(client_and_service):
    client, _ = client_and_service
    resp = client.post(
        "/api/v1/media/999999/archive",
        headers={"X-API-Key": "testkey"},
        json={},
    )
    assert resp.status_code == 404, resp.text


# ---------- the actual saga fix, proven concretely ----------

@pytest.mark.asyncio
async def test_archive_media_phase1_commits_before_phase2_io_resolves():
    """Доказывает, что резервирование (фаза 1, status='archiving') реально
    коммитится в отдельной транзакции ДО начала Telegram I/O (фаза 2):
    хук на get_file_url (первый вызов внутри _copy_to_archive) открывает
    СВЕЖУЮ сессию и читает статус синхронно, до того как archive_media
    вернёт управление. Если бы обе фазы жили в одной незакоммиченной
    транзакции (старый баг), свежая сессия видела бы старый статус "active".
    """
    from app.services.media_storage import MediaStorageService

    svc = MediaStorageService.__new__(MediaStorageService)
    svc.channels_cache = {}
    _create_archive_channel()
    media_id = _create_media_file(status="active")

    observed = {}

    class ObservingTelegram(FakeTelegram):
        async def get_file_url(self, file_id):
            # В этот момент фаза 1 уже должна была закоммититься.
            status, _ = _get_status_and_lock(media_id)
            observed["status_during_phase2_io"] = status
            return await super().get_file_url(file_id)

    svc.telegram = ObservingTelegram()

    result = await svc.archive_media(media_id)

    assert result is True
    assert observed["status_during_phase2_io"] == "archiving"
    final_status, _ = _get_status_and_lock(media_id)
    assert final_status == "archived"


@pytest.mark.asyncio
async def test_archive_media_compensates_on_io_failure():
    """Если Telegram I/O в фазе 2 падает — статус должен вернуться в
    "active", а не застрять в "archiving"."""
    svc = _make_service(fail_on={"get_file_url"})
    _create_archive_channel()
    media_id = _create_media_file(status="active")

    result = await svc.archive_media(media_id)

    assert result is False
    status, locked = _get_status_and_lock(media_id)
    assert status == "active"
    assert locked is False


@pytest.mark.asyncio
async def test_delete_media_compensates_on_io_failure():
    svc = _make_service(fail_on={"delete_message"})
    media_id = _create_media_file(status="active")

    result = await svc.delete_media(media_id)

    assert result is False
    status, _ = _get_status_and_lock(media_id)
    assert status == "active"


# ---------- the race, both orderings ----------

@pytest.mark.asyncio
async def test_race_lock_wins_first_then_archive_fails():
    from app.services.media_storage import PublicationReservationError

    svc = _make_service()
    _create_archive_channel()
    media_id = _create_media_file(status="active")

    lock_result = await svc.acquire_publication_lock(media_id)
    assert lock_result is True

    with pytest.raises(PublicationReservationError):
        await svc.archive_media(media_id)


@pytest.mark.asyncio
async def test_race_archive_reservation_wins_first_then_lock_fails():
    """Opposite ordering of the race: archive_media's phase-1 reservation
    (status -> "archiving") wins first. A concurrent acquire_publication_lock
    call on the same id, issued while status is still "archiving" (i.e.
    before phase 2 completes), must lose — the WHERE status='active' clause
    excludes it.

    We observe the "still archiving" window the same way as the two-phase
    test above: a hook on the first Telegram call made from phase 2."""
    svc = _make_service()
    _create_archive_channel()
    media_id = _create_media_file(status="active")

    observed = {}

    class BlockingTelegram(FakeTelegram):
        async def get_file_url(self, file_id):
            # Phase 1 has already committed status="archiving" by now.
            lock_result = await svc.acquire_publication_lock(media_id)
            observed["lock_result_during_archiving"] = lock_result
            return await super().get_file_url(file_id)

    svc.telegram = BlockingTelegram()

    result = await svc.archive_media(media_id)

    assert result is True
    assert observed["lock_result_during_archiving"] is False


# ---------- list_publication_locks ----------

@pytest.mark.asyncio
async def test_list_publication_locks_returns_only_locked_with_pagination():
    svc = _make_service()
    locked_ids = [
        _create_media_file(status="active", publication_locked=True) for _ in range(3)
    ]
    _create_media_file(status="active", publication_locked=False)
    _create_media_file(status="archived", publication_locked=False)

    rows, total = await svc.list_publication_locks(limit=2, offset=0)
    assert total == 3
    assert len(rows) == 2
    returned_ids = {r["id"] for r in rows}
    assert returned_ids.issubset(set(locked_ids))
    for r in rows:
        assert "status" in r
        assert "updated_at" in r

    rows_page2, total2 = await svc.list_publication_locks(limit=2, offset=2)
    assert total2 == 3
    assert len(rows_page2) == 1


def test_publication_locks_endpoint_not_shadowed_by_bare_media_id(client_and_service):
    """Route-ordering regression: /media/publication-locks должен резолвиться
    в свой handler, а не в GET /{media_id} (что дало бы 422 — 'publication-locks'
    не int)."""
    client, _ = client_and_service
    media_id = _create_media_file(status="active", publication_locked=True)

    resp = client.get(
        "/api/v1/media/publication-locks",
        headers={"X-API-Key": "testkey"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body and "total" in body and "limit" in body and "offset" in body
    assert any(item["id"] == media_id for item in body["items"])


# ---------- publication-lock endpoints ----------

def test_acquire_and_release_lock_endpoints(client_and_service):
    client, _ = client_and_service
    media_id = _create_media_file(status="active")

    resp = client.post(
        f"/api/v1/media/{media_id}/publication-lock",
        headers={"X-API-Key": "testkey"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"media_id": media_id, "publication_locked": True}

    _, locked = _get_status_and_lock(media_id)
    assert locked is True

    resp2 = client.delete(
        f"/api/v1/media/{media_id}/publication-lock",
        headers={"X-API-Key": "testkey"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json() == {"media_id": media_id, "publication_locked": False}

    _, locked2 = _get_status_and_lock(media_id)
    assert locked2 is False


def test_acquire_lock_endpoint_404_on_non_active(client_and_service):
    client, _ = client_and_service
    media_id = _create_media_file(status="archived")

    resp = client.post(
        f"/api/v1/media/{media_id}/publication-lock",
        headers={"X-API-Key": "testkey"},
    )
    assert resp.status_code == 404, resp.text
