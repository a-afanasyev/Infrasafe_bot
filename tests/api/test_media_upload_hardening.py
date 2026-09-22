"""Аудит #9: POST /api/v2/media/upload — маркер, роль фотоотчёта, DoS-гигиена.

* A9-P2-1 — `_append_media_marker` брал строку `FOR UPDATE`, но `Request` уже
  лежал в identity map сессии (его загрузил `check_request_access`), и ORM
  отдавал УСТАРЕВШИЙ `media_files`: `[*stale, new]` затирал маркер параллельной
  загрузки. Гейт доступа здесь настоящий — именно он кладёт строку в identity
  map, с заглушкой дефект не воспроизводится.
* A9-P2-3 — `completion_*` (фотоотчёт исполнителя) может грузить только
  назначенный исполнитель или менеджер; житель с доступом к заявке — 403.
* A9-P3-4 — файл читается не больше MAX+1 байт, маршрут под `@limiter.limit`,
  таймаут к media-service меньше бюджета edge (30 с), сбой транспорта → 503,
  битый JSON ответа → 502.
"""
import io
import json
import time
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User

RN = "260922-701"
JPEG = b"\xff\xd8\xff\xe0jpegdata"


def _media_payload(media_id: int) -> dict:
    return {
        "media_file": {"id": media_id, "file_type": "photo", "category": "request_photo"},
        "file_url": f"/api/v1/media/{media_id}/file",
        "message": "ok",
    }


class _StubResp:
    def __init__(self, payload=None, status_code=200, raw=None):
        self.status_code = status_code
        self._payload = payload
        self._raw = raw

    def json(self):
        if self._raw is not None:
            return json.loads(self._raw)
        return self._payload


def _install_media_stub(monkeypatch, *, on_post=None, response=None, raise_exc=None):
    """Подменяет httpx.AsyncClient прокси. `on_post` — корутина, выполняемая
    ВНУТРИ исходящего вызова: окно между гейтом доступа и записью маркера."""
    from uk_management_bot.api.routes import media_proxy

    captured = {"init_kwargs": None, "calls": 0}

    class _StubClient:
        def __init__(self, *a, **k):
            captured["init_kwargs"] = k

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            captured["calls"] += 1
            if raise_exc is not None:
                raise raise_exc
            if on_post is not None:
                await on_post()
            return response or _StubResp(_media_payload(42))

    monkeypatch.setattr(media_proxy.httpx, "AsyncClient", _StubClient)
    monkeypatch.setattr(media_proxy.settings, "MEDIA_SERVICE_URL", "http://stub-media")
    return captured


async def _seed_request(db_session, *, user_id=999999, executor_id=None, media_files=None):
    db_session.add(RequestModel(
        request_number=RN, user_id=user_id, category="Сантехника", urgency="Срочная",
        description="t", address="ул. Тестовая, 1", apartment_id=None,
        status="В работе", source="bot", media_files=media_files or [],
        executor_id=executor_id,
    ))
    await db_session.commit()


async def _media_files(db_session):
    row = (await db_session.execute(
        select(RequestModel).where(RequestModel.request_number == RN)
        .execution_options(populate_existing=True)
    )).scalar_one()
    return row.media_files


async def _add_user(db_session, *, telegram_id, roles, specialization=None) -> User:
    user = User(
        telegram_id=telegram_id, first_name="U", roles=json.dumps(roles),
        active_role=roles[0], status="approved", specialization=specialization,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _act_as(user: User) -> None:
    async def _current():
        return user

    app.dependency_overrides[get_current_user] = _current


async def _upload(client, category="request_photo", content=JPEG, headers=None):
    return await client.post(
        "/api/v2/media/upload",
        files=[("file", ("x.jpg", io.BytesIO(content), "image/jpeg"))],
        data={"request_number": RN, "category": category},
        headers=headers,
    )


# ── A9-P2-1: stale identity map ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_marker_survives_stale_identity_map(
    client, db_session, db_session_factory, monkeypatch,
):
    """Параллельная загрузка дописала маркер 41 ПОСЛЕ того, как гейт доступа
    этого запроса загрузил заявку. Запись маркера 42 обязана его сохранить."""
    await _seed_request(db_session)

    async def concurrent_upload_commits():
        async with db_session_factory() as other:
            row = (await other.execute(
                select(RequestModel).where(RequestModel.request_number == RN)
            )).scalar_one()
            row.media_files = [{"media_id": 41, "type": "photo"}]
            await other.commit()

    _install_media_stub(monkeypatch, on_post=concurrent_upload_commits)

    resp = await _upload(client)

    assert resp.status_code == 200, resp.text
    assert await _media_files(db_session) == [
        {"media_id": 41, "type": "photo"},
        {"media_id": 42, "type": "photo"},
    ]


@pytest.mark.asyncio
async def test_append_marker_rereads_row_already_in_session(db_session_factory, manager_user):
    """Прямая проверка `_append_media_marker`: строка уже в identity map
    (как после `check_request_access`), колонку меняет другая сессия."""
    from uk_management_bot.api.dependencies_access import check_request_access
    from uk_management_bot.api.routes.media_proxy import _append_media_marker

    async with db_session_factory() as seed:
        await _seed_request(seed)

    async with db_session_factory() as db:
        # Ссылку держим, как держит её эндпоинт (проверка роли фотоотчёта):
        # identity map слабый, и без живой ссылки объект был бы уже собран —
        # дефект маскировался бы сборщиком мусора, а не кодом.
        loaded = await check_request_access(RN, db, manager_user)
        async with db_session_factory() as other:
            row = (await other.execute(
                select(RequestModel).where(RequestModel.request_number == RN)
            )).scalar_one()
            row.media_files = [{"media_id": 41, "type": "photo"}]
            await other.commit()

        await _append_media_marker(db, RN, 42, "photo")
        assert loaded in db

    async with db_session_factory() as check:
        assert await _media_files(check) == [
            {"media_id": 41, "type": "photo"},
            {"media_id": 42, "type": "photo"},
        ]


@pytest.mark.asyncio
async def test_append_marker_missing_row_is_noop(db_session):
    """Заявку удалили между гейтом и записью маркера — не падаем."""
    from uk_management_bot.api.routes.media_proxy import _append_media_marker

    await _append_media_marker(db_session, RN, 42, "photo")


# ── A9-P2-3: фотоотчёт — только исполнитель или менеджер ───────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["completion_photo", "completion_video", "completion_document"])
async def test_resident_owner_cannot_upload_completion(client, db_session, resident_user, monkeypatch, category):
    await _seed_request(db_session, user_id=resident_user.id)
    captured = _install_media_stub(monkeypatch)
    _act_as(resident_user)

    resp = await _upload(client, category=category)

    assert resp.status_code == 403, resp.text
    assert captured["calls"] == 0, "отказ обязан случиться ДО похода в media-service"


@pytest.mark.asyncio
async def test_resident_owner_still_uploads_request_photo(client, db_session, resident_user, monkeypatch):
    await _seed_request(db_session, user_id=resident_user.id)
    _install_media_stub(monkeypatch)
    _act_as(resident_user)

    resp = await _upload(client, category="request_photo")

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_owner_with_executor_role_but_not_assigned_cannot_upload_completion(
    client, db_session, monkeypatch,
):
    """Владелец заявки, у которого есть роль executor, но заявка не на нём:
    доступ «как владелец» не даёт права на фотоотчёт."""
    owner = await _add_user(db_session, telegram_id=7001, roles=["executor", "applicant"])
    await _seed_request(db_session, user_id=owner.id)
    captured = _install_media_stub(monkeypatch)
    _act_as(owner)

    resp = await _upload(client, category="completion_photo")

    assert resp.status_code == 403, resp.text
    assert captured["calls"] == 0


@pytest.mark.asyncio
async def test_assigned_executor_uploads_completion(client, db_session, monkeypatch):
    executor = await _add_user(db_session, telegram_id=7002, roles=["executor"])
    await _seed_request(db_session, executor_id=executor.id)
    _install_media_stub(monkeypatch)
    _act_as(executor)

    resp = await _upload(client, category="completion_photo")

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_executor_who_owns_and_is_assigned_uploads_completion(client, db_session, monkeypatch):
    """Канон проверяет «владелец» раньше исполнителя — назначенный исполнитель,
    он же автор заявки, не должен из-за этого получить 403."""
    executor = await _add_user(db_session, telegram_id=7005, roles=["executor"])
    await _seed_request(db_session, user_id=executor.id, executor_id=executor.id)
    _install_media_stub(monkeypatch)
    _act_as(executor)

    resp = await _upload(client, category="completion_photo")

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_group_assigned_executor_on_shift_uploads_completion(client, db_session, monkeypatch):
    executor = await _add_user(db_session, telegram_id=7003, roles=["executor"], specialization="plumber")
    await _seed_request(db_session)
    db_session.add(RequestAssignment(
        request_number=RN, assignment_type="group", group_specialization="plumber",
        executor_id=None, status="active", created_by=executor.id,
    ))
    db_session.add(Shift(
        user_id=executor.id, status="active",
        start_time=datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc),
    ))
    await db_session.commit()
    _install_media_stub(monkeypatch)
    _act_as(executor)

    resp = await _upload(client, category="completion_photo")

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_unassigned_executor_gets_403(client, db_session, monkeypatch):
    stranger = await _add_user(db_session, telegram_id=7004, roles=["executor"])
    await _seed_request(db_session)
    _install_media_stub(monkeypatch)
    _act_as(stranger)

    resp = await _upload(client, category="completion_photo")

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_manager_uploads_completion(client, db_session, monkeypatch):
    await _seed_request(db_session)
    _install_media_stub(monkeypatch)

    resp = await _upload(client, category="completion_photo")

    assert resp.status_code == 200, resp.text


# ── A9-P3-4: чтение, таймауты, ошибки апстрима, рейт-лимит ─────────────


@pytest.mark.asyncio
async def test_upload_reads_at_most_max_plus_one_bytes(client, db_session, monkeypatch):
    from starlette.datastructures import UploadFile

    from uk_management_bot.api.routes import media_proxy

    await _seed_request(db_session)
    captured = _install_media_stub(monkeypatch)
    monkeypatch.setattr(media_proxy, "_MEDIA_MAX_BYTES", 16)
    sizes = []
    original_read = UploadFile.read

    async def spy_read(self, size=-1):
        sizes.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", spy_read)

    resp = await _upload(client, content=JPEG + b"\x00" * 64)

    assert resp.status_code == 422, resp.text
    assert sizes == [17], "файл читается с потолком MAX+1, а не целиком"
    assert captured["calls"] == 0


@pytest.mark.asyncio
async def test_upload_timeout_fits_edge_budget(client, db_session, monkeypatch):
    await _seed_request(db_session)
    captured = _install_media_stub(monkeypatch)

    resp = await _upload(client)

    assert resp.status_code == 200, resp.text
    timeout = captured["init_kwargs"]["timeout"]
    assert isinstance(timeout, httpx.Timeout), timeout
    assert timeout.read is not None and timeout.read <= 25
    assert timeout.connect is not None and timeout.connect <= 5


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [
    httpx.ConnectError("refused"),
    httpx.ReadTimeout("slow"),
])
async def test_media_transport_error_is_503(client, db_session, monkeypatch, exc):
    await _seed_request(db_session)
    _install_media_stub(monkeypatch, raise_exc=exc)

    resp = await _upload(client)

    assert resp.status_code == 503, resp.text
    assert await _media_files(db_session) == []


@pytest.mark.asyncio
async def test_media_invalid_json_is_502(client, db_session, monkeypatch):
    await _seed_request(db_session)
    _install_media_stub(monkeypatch, response=_StubResp(raw="<html>oops</html>"))

    resp = await _upload(client)

    assert resp.status_code == 502, resp.text
    assert await _media_files(db_session) == []


def _ip(salt: int = 0) -> dict:
    # Свой октет TEST-NET-3 на тест: в dev-контейнере счётчик живёт в Redis.
    octet = (((time.monotonic_ns() >> 4) & 0xFF) + salt) % 256 or 1
    return {"X-Real-IP": f"203.0.113.{min(octet, 254)}"}


@pytest.mark.asyncio
async def test_upload_rate_limited(client, monkeypatch):
    """Лимитер считает обращения, а не успехи: невалидный номер (422) тоже
    расходует квоту, поэтому БД и media-service тесту не нужны."""
    from uk_management_bot.api.routes.media_proxy import UPLOAD_RATE_LIMIT

    limit = int(UPLOAD_RATE_LIMIT.split("/")[0])
    headers = _ip(7)
    for i in range(limit):
        r = await client.post(
            "/api/v2/media/upload",
            files=[("file", ("x.jpg", io.BytesIO(JPEG), "image/jpeg"))],
            data={"request_number": "bad", "category": "request_photo"},
            headers=headers,
        )
        assert r.status_code != 429, f"вызов {i + 1} упёрся в лимит раньше срока"

    r = await client.post(
        "/api/v2/media/upload",
        files=[("file", ("x.jpg", io.BytesIO(JPEG), "image/jpeg"))],
        data={"request_number": "bad", "category": "request_photo"},
        headers=headers,
    )
    assert r.status_code == 429, r.text
