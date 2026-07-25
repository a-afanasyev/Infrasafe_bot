"""Тесты менеджерского REST API визуальных отчётов «до/после» (T7,
/api/v2/work-reports). Роутер тонкий — вся доменная логика уже покрыта
`test_work_reports_saga.py`/`test_work_report_media.py`/`test_work_reports_sync.py`
(T5/T6); здесь проверяется HTTP-обвязка: фиче-флаг → 404, RBAC → 403,
маппинг доменных ошибок → HTTP-коды, форма ответов.

`FakeMediaClient` — тот же паттерн, что и в `test_work_report_media.py` /
`test_work_reports_saga.py`, адаптированный под `get_media_client()`
(не FastAPI-dependency — обычная функция, импортированная в роутере
напрямую, поэтому патчится по имени в модуле роутера).
"""
import copy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uk_management_bot.api.work_reports.router as work_reports_router
from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.database.models.yard import Yard

BASE = "/api/v2/work-reports"


# ── Helpers ──────────────────────────────────────────────────────────


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", True)


def _patch_media_client(monkeypatch, fake_client) -> None:
    """The router calls `get_media_client()` directly (not a FastAPI
    Depends), so it's patched by name in the router module — same
    module-level-function patching already used for `httpx`/`settings` in
    `api/routes/media_proxy.py`'s own test coverage."""
    monkeypatch.setattr(work_reports_router, "get_media_client", lambda: fake_client)


def _reset_reconcile_throttle(monkeypatch) -> None:
    monkeypatch.setattr(work_reports_router, "_last_reconcile_at", None)


@contextmanager
def _as_user(user: User):
    """Временно подменить текущего пользователя поверх client-фикстуры
    (паттерн из test_materials.py)."""
    prev = app.dependency_overrides.get(get_current_user)

    async def override():
        return user

    app.dependency_overrides[get_current_user] = override
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = prev


def _photo(id_, *, file_type="photo", status="active", file_size=1024, mime_type="image/jpeg"):
    return {
        "id": id_, "file_type": file_type, "status": status,
        "file_size": file_size, "mime_type": mime_type,
    }


class FakeMediaClient:
    """Заглушка media_client — get_request_media (T5-паттерн) + acquire/
    release publication lock + list_publication_locks (T6-паттерн)."""

    def __init__(self, by_category=None, list_locks_items=None):
        self._by_category = by_category or {}
        self._list_locks_items = list_locks_items if list_locks_items is not None else []
        self.acquire_calls: list[int] = []
        self.release_calls: list[int] = []
        self.resolve_stale_calls: list[int] = []
        self.warm_calls: list[list[int]] = []

    async def warm_previews(self, media_ids: list[int]) -> dict:
        """Прогрев превью — оптимизация; сага и тик зовут его best-effort."""
        self.warm_calls.append(list(media_ids))
        return {"warmed": len(media_ids), "already_cached": 0, "failed": 0}

    async def resolve_stale_transitions(self, older_than_minutes: int = 15) -> dict:
        self.resolve_stale_calls.append(older_than_minutes)
        return {"archiving_reverted": 0, "deleting_finalized": 0}

    async def get_request_media(self, request_number: str, category: str, limit: int = 50):
        return self._by_category.get(category, [])

    async def acquire_publication_lock(self, media_id: int) -> bool:
        self.acquire_calls.append(media_id)
        return True

    async def release_publication_lock(self, media_id: int) -> bool:
        self.release_calls.append(media_id)
        return True

    async def list_publication_locks(self, limit: int = 200, offset: int = 0) -> dict:
        items = self._list_locks_items[offset: offset + limit]
        return {"items": items, "total": len(self._list_locks_items), "limit": limit, "offset": offset}


async def _mk_yard(db: AsyncSession, name: str) -> Yard:
    yard = Yard(name=name)
    db.add(yard)
    await db.commit()
    await db.refresh(yard)
    return yard


async def _mk_building(db: AsyncSession, yard_id: int, address: str) -> Building:
    building = Building(address=address, yard_id=yard_id)
    db.add(building)
    await db.commit()
    await db.refresh(building)
    return building


async def _mk_request(db: AsyncSession, number: str, **kwargs) -> Request:
    defaults = dict(
        user_id=1, category="plumbing", status="Принято", description="test",
        urgency="low", is_returned=False, address_type="yard",
    )
    defaults.update(kwargs)
    req = Request(request_number=number, **defaults)
    db.add(req)
    await db.commit()
    return req


async def _seed_autopost(db: AsyncSession, *, since: datetime) -> None:
    """Включить автопост с бэкдейтом — иначе `floor_ts` равен моменту включения
    и синк ничего не создаёт (тот же приём, что `_seed_board_config` в
    test_work_reports_sync.py)."""
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["work_reports"]["autopost"] = True
    data["work_reports"]["autopost_since"] = since.isoformat()
    db.add(BoardConfig(id=1, data=data, updated_by=None))
    await db.commit()


async def _mk_report(db: AsyncSession, number: str, **kwargs) -> WorkReport:
    defaults = dict(
        category_key="plumbing", address_public="Двор Х",
        performed_at=datetime.now(timezone.utc),
        before_media_ids=[], after_media_ids=[], media_meta=[], locked_media_ids=[],
        status="pending", source="manual",
    )
    defaults.update(kwargs)
    report = WorkReport(request_number=number, **defaults)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


# ── Flag off → 404 everywhere ───────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_off_list_404(client: AsyncClient):
    resp = await client.get(BASE)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_flag_off_create_404(client: AsyncClient):
    resp = await client.post(BASE, json={"request_number": "260725-001"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_flag_off_publish_404(client: AsyncClient):
    resp = await client.post(f"{BASE}/1/publish")
    assert resp.status_code == 404


# ── RBAC: non-manager → 403 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_manager_get_list_403(client: AsyncClient, resident_user, monkeypatch):
    _enable(monkeypatch)
    with _as_user(resident_user):
        resp = await client.get(BASE)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_manager_create_403(client: AsyncClient, resident_user, monkeypatch):
    _enable(monkeypatch)
    with _as_user(resident_user):
        resp = await client.post(BASE, json={"request_number": "260725-001"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unapproved_manager_403(client: AsyncClient, db_session, monkeypatch):
    """Роль manager есть, но пользователь ещё не approved → 403.

    Роутер гейтится `require_approved_roles`, а не `require_roles`: модуль
    публикует контент в открытый интернет, поэтому менеджер, сидящий на
    модерации, управлять им не должен.
    """
    _enable(monkeypatch)
    pending_manager = User(
        telegram_id=777333, username="pendingmgr", first_name="Pending",
        roles='["manager"]', active_role="manager", status="pending",
    )
    db_session.add(pending_manager)
    await db_session.commit()

    with _as_user(pending_manager):
        resp = await client.get(BASE)
    assert resp.status_code == 403


# ── GET "" list ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_empty_initially(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    resp = await client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}


@pytest.mark.asyncio
async def test_list_filters_by_status(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_report(db_session, "260725-201", status="pending")
    await _mk_report(db_session, "260725-202", status="published")

    resp = await client.get(BASE, params={"status": "published"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["request_number"] == "260725-202"


@pytest.mark.asyncio
async def test_list_pagination(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    for i in range(5):
        await _mk_report(db_session, f"260725-21{i}", status="pending")

    resp = await client.get(BASE, params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0

    resp2 = await client.get(BASE, params={"limit": 2, "offset": 4})
    assert len(resp2.json()["items"]) == 1


# ── POST "" create ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_structured_address_happy_path(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Создания")
    await _mk_request(
        db_session, "260725-300", status="Принято", address_type="yard", yard_id=yard.id,
    )

    resp = await client.post(BASE, json={"request_number": "260725-300"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["request_number"] == "260725-300"
    assert body["status"] == "pending"
    assert body["source"] == "manual"
    assert body["address_public"] == "Двор Создания"


@pytest.mark.asyncio
async def test_create_409_duplicate_request_number(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_report(db_session, "260725-301")

    resp = await client.post(BASE, json={"request_number": "260725-301"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_404_unknown_request(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    resp = await client.post(BASE, json={"request_number": "260725-999"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_409_ineligible_wrong_status(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Неготов")
    await _mk_request(
        db_session, "260725-302", status="Новая", address_type="yard", yard_id=yard.id,
    )

    resp = await client.post(BASE, json={"request_number": "260725-302"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_409_ineligible_returned(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Возврат")
    await _mk_request(
        db_session, "260725-303", status="Принято", is_returned=True,
        address_type="yard", yard_id=yard.id,
    )

    resp = await client.post(BASE, json={"request_number": "260725-303"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_legacy_requires_exactly_one_id_neither_given(
    client: AsyncClient, db_session, monkeypatch
):
    _enable(monkeypatch)
    await _mk_request(db_session, "260725-304", status="Принято", address_type="legacy")

    resp = await client.post(BASE, json={"request_number": "260725-304"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_legacy_requires_exactly_one_id_both_given(
    client: AsyncClient, db_session, monkeypatch
):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Легаси")
    building = await _mk_building(db_session, yard.id, "ул. Легаси, 1")
    await _mk_request(db_session, "260725-305", status="Принято", address_type="legacy")

    resp = await client.post(
        BASE,
        json={"request_number": "260725-305", "building_id": building.id, "yard_id": yard.id},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_legacy_with_valid_building_id_201(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Легаси-2")
    building = await _mk_building(db_session, yard.id, "ул. Легаси, 2")
    await _mk_request(db_session, "260725-306", status="Принято", address_type="legacy")

    resp = await client.post(
        BASE, json={"request_number": "260725-306", "building_id": building.id}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["address_public"] == "ул. Легаси, 2 (Двор Легаси-2)"


@pytest.mark.asyncio
async def test_create_structured_address_override_attempt_422(
    client: AsyncClient, db_session, monkeypatch
):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Структ")
    building = await _mk_building(db_session, yard.id, "ул. Структ, 1")
    await _mk_request(
        db_session, "260725-307", status="Принято", address_type="yard", yard_id=yard.id,
    )

    resp = await client.post(
        BASE, json={"request_number": "260725-307", "building_id": building.id}
    )
    assert resp.status_code == 422
    assert "address_override_not_allowed" in resp.text


# ── POST /sync ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_returns_summary_shape(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    _reset_reconcile_throttle(monkeypatch)
    _patch_media_client(monkeypatch, None)  # media service unconfigured — reconcile skipped

    resp = await client.post(f"{BASE}/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"sync", "autopublish", "revoked", "reconcile", "reconcile_error"}
    # Без media-клиента и автопубликация, и сверка пропускаются: обе ходят в
    # media-service (autofill/lock), поэтому без него им нечего делать.
    assert body["reconcile"] is None
    assert body["autopublish"] is None
    assert body["reconcile_error"] is None


@pytest.mark.asyncio
async def test_sync_reconcile_throttled_on_second_rapid_call(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    _reset_reconcile_throttle(monkeypatch)
    fake = FakeMediaClient()
    _patch_media_client(monkeypatch, fake)

    first = await client.post(f"{BASE}/sync")
    assert first.status_code == 200
    assert first.json()["reconcile"] is not None

    second = await client.post(f"{BASE}/sync")
    assert second.status_code == 200
    assert second.json()["reconcile"] is None


class _LocksInventoryDown(FakeMediaClient):
    """media-service отвечает ошибкой на инвентаризацию локов.

    `list_publication_locks` в реальном клиенте бросает намеренно (глотать
    нельзя: по пустому списку сверка сняла бы живые локи), поэтому заглушка
    воспроизводит именно исключение, а не пустой ответ.
    """

    async def list_publication_locks(self, limit: int = 200, offset: int = 0) -> dict:
        raise RuntimeError("media-service unreachable")


@pytest.mark.asyncio
async def test_sync_survives_failing_lock_reconciliation(
    client: AsyncClient, db_session, monkeypatch, manager_user
):
    """Упавшая сверка локов не должна ронять /sync.

    Синк, автопубликация и отзыв к этому моменту уже закоммичены, а /sync —
    единственный вход менеджера в очередь: 500 здесь означал бы «очередь не
    открывается, пока лежит media-service».
    """
    _enable(monkeypatch)
    _reset_reconcile_throttle(monkeypatch)
    _patch_media_client(monkeypatch, _LocksInventoryDown())
    await _seed_autopost(db_session, since=datetime.now(timezone.utc) - timedelta(days=1))
    yard = await _mk_yard(db_session, "Двор")
    await _mk_request(db_session, "260725-950", yard_id=yard.id)

    resp = await client.post(f"{BASE}/sync")

    assert resp.status_code == 200
    body = resp.json()
    # Полезная работа сделана и видна в ответе...
    assert body["sync"]["created"] == 1
    # ...а провал сверки назван явно, а не проглочен молчанием.
    assert body["reconcile"] is None
    assert body["reconcile_error"] == "RuntimeError"
    assert (await db_session.execute(
        select(WorkReport).where(WorkReport.request_number == "260725-950")
    )).scalars().one().status == "pending"


@pytest.mark.asyncio
async def test_sync_throttles_reconcile_even_after_failure(client: AsyncClient, monkeypatch):
    """Метка троттла ставится и при провале сверки.

    Иначе `_last_reconcile_at` не обновлялся бы, и каждый следующий /sync снова
    упирался бы в недоступный media-service — на проде это таймаут на таймауте.
    """
    _enable(monkeypatch)
    _reset_reconcile_throttle(monkeypatch)
    _patch_media_client(monkeypatch, _LocksInventoryDown())

    first = await client.post(f"{BASE}/sync")
    assert first.status_code == 200
    assert first.json()["reconcile_error"] == "RuntimeError"

    second = await client.post(f"{BASE}/sync")
    assert second.status_code == 200
    # Сверку даже не пытались запустить — значит метка времени была поставлена.
    assert second.json()["reconcile_error"] is None
    assert second.json()["reconcile"] is None


# ── autofill ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_autofill_one_happy_path_sets_pending(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-320", status="needs_media")
    fake = FakeMediaClient(by_category={
        "request_photo": [_photo(1)],
        "completion_photo": [_photo(2)],
    })
    _patch_media_client(monkeypatch, fake)

    resp = await client.post(f"{BASE}/{report.id}/autofill")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["before_media_ids"] == [1]
    assert body["after_media_ids"] == [2]


@pytest.mark.asyncio
async def test_autofill_one_empty_media_sets_needs_media(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-321", status="pending")
    fake = FakeMediaClient(by_category={"request_photo": [], "completion_photo": []})
    _patch_media_client(monkeypatch, fake)

    resp = await client.post(f"{BASE}/{report.id}/autofill")
    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_media"


@pytest.mark.asyncio
async def test_autofill_one_503_without_media_client(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-322")
    _patch_media_client(monkeypatch, None)

    resp = await client.post(f"{BASE}/{report.id}/autofill")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_autofill_pending_batch_happy_path(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    r1 = await _mk_report(db_session, "260725-323", status="pending")
    r2 = await _mk_report(db_session, "260725-324", status="pending")
    fake = FakeMediaClient(by_category={
        "request_photo": [_photo(1)],
        "completion_photo": [_photo(2)],
    })
    _patch_media_client(monkeypatch, fake)

    resp = await client.post(f"{BASE}/autofill-pending")
    assert resp.status_code == 200
    assert resp.json() == {"processed": 2}

    # `client` served the request through a SEPARATE session (see conftest's
    # `override_get_db`) — this session's identity map hasn't seen the
    # commit, so a plain re-select would return stale cached attributes.
    # `populate_existing()` forces attributes to be refreshed from the row.
    reloaded = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.id == r1.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert reloaded.before_media_ids == [1]
    reloaded2 = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.id == r2.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert reloaded2.after_media_ids == [2]


# ── PATCH /{id} ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_category_key(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-330", category_key="plumbing")

    resp = await client.patch(f"{BASE}/{report.id}", json={"category_key": "electricity"})
    assert resp.status_code == 200
    assert resp.json()["category_key"] == "electricity"


@pytest.mark.asyncio
async def test_patch_media_reselection_valid(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-331", status="needs_media")
    fake = FakeMediaClient(by_category={
        "request_photo": [_photo(5)],
        "completion_photo": [_photo(6)],
    })
    _patch_media_client(monkeypatch, fake)

    resp = await client.patch(
        f"{BASE}/{report.id}", json={"before_media_ids": [5], "after_media_ids": [6]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["before_media_ids"] == [5]
    assert body["after_media_ids"] == [6]
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_patch_media_reselection_invalid_id_422(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-332", status="pending")
    fake = FakeMediaClient(by_category={"request_photo": [_photo(1)], "completion_photo": [_photo(2)]})
    _patch_media_client(monkeypatch, fake)

    resp = await client.patch(
        f"{BASE}/{report.id}", json={"before_media_ids": [999], "after_media_ids": [2]}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_address_override_on_legacy_applied(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Патч-Легаси")
    building = await _mk_building(db_session, yard.id, "ул. Патч-Легаси, 9")
    await _mk_request(db_session, "260725-333", status="Принято", address_type="legacy")
    report = await _mk_report(db_session, "260725-333", status="pending", address_public="old")

    resp = await client.patch(f"{BASE}/{report.id}", json={"building_id": building.id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["address_public"] == "ул. Патч-Легаси, 9 (Двор Патч-Легаси)"


@pytest.mark.asyncio
async def test_patch_address_override_on_structured_422(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    yard = await _mk_yard(db_session, "Двор Патч-Структ")
    building = await _mk_building(db_session, yard.id, "ул. Патч-Структ, 3")
    await _mk_request(
        db_session, "260725-334", status="Принято", address_type="yard", yard_id=yard.id,
    )
    report = await _mk_report(db_session, "260725-334", status="pending")

    resp = await client.patch(f"{BASE}/{report.id}", json={"building_id": building.id})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_from_published_status_409(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-335", status="published")

    resp = await client.patch(f"{BASE}/{report.id}", json={"category_key": "electricity"})
    assert resp.status_code == 409


# ── POST /{id}/publish ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_happy_path_200(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_request(db_session, "260725-340", status="Принято", address_type=None)
    report = await _mk_report(
        db_session, "260725-340", status="pending",
        before_media_ids=[1], after_media_ids=[2],
    )
    fake = FakeMediaClient(by_category={"request_photo": [_photo(1)], "completion_photo": [_photo(2)]})
    _patch_media_client(monkeypatch, fake)

    resp = await client.post(f"{BASE}/{report.id}/publish")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None


@pytest.mark.asyncio
async def test_publish_409_wrong_starting_status(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-341", status="published")
    _patch_media_client(monkeypatch, FakeMediaClient())

    resp = await client.post(f"{BASE}/{report.id}/publish")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_publish_422_missing_media(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_request(db_session, "260725-342", status="Принято", address_type=None)
    report = await _mk_report(db_session, "260725-342", status="pending", before_media_ids=[], after_media_ids=[])
    _patch_media_client(monkeypatch, FakeMediaClient())

    resp = await client.post(f"{BASE}/{report.id}/publish")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_publish_503_without_media_client(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-343", status="pending")
    _patch_media_client(monkeypatch, None)

    resp = await client.post(f"{BASE}/{report.id}/publish")
    assert resp.status_code == 503


# ── POST /{id}/unpublish ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unpublish_happy_path(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-350", status="published", locked_media_ids=[1])
    _patch_media_client(monkeypatch, FakeMediaClient())

    resp = await client.post(f"{BASE}/{report.id}/unpublish", json={"reason": "bad photo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "bad photo"


@pytest.mark.asyncio
async def test_unpublish_409_wrong_status(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-351", status="pending")
    _patch_media_client(monkeypatch, FakeMediaClient())

    resp = await client.post(f"{BASE}/{report.id}/unpublish", json={})
    assert resp.status_code == 409


# ── POST /{id}/reject ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_happy_path(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-360", status="pending")

    resp = await client.post(f"{BASE}/{report.id}/reject", json={"reason": "not suitable"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "not suitable"


@pytest.mark.asyncio
async def test_reject_409_wrong_status(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-361", status="published")

    resp = await client.post(f"{BASE}/{report.id}/reject", json={"reason": "x"})
    assert resp.status_code == 409


# ── POST /{id}/reopen ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reopen_happy_path(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-370", status="rejected", reject_reason="old")

    resp = await client.post(f"{BASE}/{report.id}/reopen")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["reject_reason"] is None


@pytest.mark.asyncio
async def test_reopen_409_wrong_status(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-371", status="pending")

    resp = await client.post(f"{BASE}/{report.id}/reopen")
    assert resp.status_code == 409


# ── PUT /settings ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_settings_updates_fields(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)

    resp = await client.put(
        f"{BASE}/settings",
        json={"autopost": True, "limit": 10, "title": {"ru": "Наши работы", "uz": "Ishlarimiz"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["autopost"] is True
    assert body["limit"] == 10
    assert body["title"] == {"ru": "Наши работы", "uz": "Ishlarimiz"}
    # Server-stamped on False→True transition, never left null.
    assert body["autopost_since"] is not None


@pytest.mark.asyncio
async def test_put_settings_extra_unknown_field_ignored(client: AsyncClient, monkeypatch):
    """`WorkReportsSettingsIn` has no `autopost_since` field at all — a client
    trying to smuggle a raw value through gets silently ignored by Pydantic's
    default extra-field behaviour (not `extra=\"forbid\"`), not a 422."""
    _enable(monkeypatch)

    resp = await client.put(
        f"{BASE}/settings",
        json={"limit": 8, "autopost_since": "2000-01-01T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["limit"] == 8
    # autopost stayed False (untouched) → autopost_since must be None, not
    # the smuggled 2000 value.
    assert body["autopost_since"] is None


# ── POST /reconcile ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_happy_path_summary_shape(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    fake = FakeMediaClient()
    _patch_media_client(monkeypatch, fake)

    resp = await client.post(f"{BASE}/reconcile")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "unstuck_publishing", "orphaned_locks_released", "missing_locks_relocked",
        # Четвёртое направление: восстановление зависших archiving/deleting на
        # стороне media-service (он один знает семантику своих переходов).
        "stale_transitions",
    }
    assert fake.resolve_stale_calls == [15]


@pytest.mark.asyncio
async def test_reconcile_503_without_media_client(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    _patch_media_client(monkeypatch, None)

    resp = await client.post(f"{BASE}/reconcile")
    assert resp.status_code == 503


# ── Валидация на границе ────────────────────────────────────────────
#
# Все четыре кейса ниже раньше проходили молча: неизвестный статус давал пустой
# список (читается как «отчётов нет»), неизвестная категория и список медиа
# любой длины доезжали до публичной ленты, а autofill мог перезаписать состав
# уже опубликованного отчёта.


@pytest.mark.asyncio
async def test_list_rejects_unknown_status_filter(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    resp = await client.get(BASE, params={"status": "pendign"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_rejects_unknown_category_key(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-901")

    resp = await client.patch(f"{BASE}/{report.id}", json={"category_key": "нет-такой"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_accepts_canonical_category_key(client: AsyncClient, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-902")

    resp = await client.patch(f"{BASE}/{report.id}", json={"category_key": "electricity"})
    assert resp.status_code == 200
    assert resp.json()["category_key"] == "electricity"


@pytest.mark.asyncio
async def test_patch_rejects_media_list_over_cap(client: AsyncClient, db_session, monkeypatch):
    """Тот же cap (MAX_MEDIA_PER_SIDE=4), что применяет autofill — ручной PATCH
    не должен быть лазейкой в обход него."""
    _enable(monkeypatch)
    report = await _mk_report(db_session, "260725-903")

    resp = await client.patch(f"{BASE}/{report.id}", json={"before_media_ids": [1, 2, 3, 4, 5]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_autofill_one_409_on_published_report(client: AsyncClient, db_session, monkeypatch):
    """Автозаполнение опубликованного отчёта перезаписало бы замороженный
    состав медиа — тот же класс поломки, что закрывает row-lock в PATCH."""
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-904", status="published",
        before_media_ids=[1], after_media_ids=[2], locked_media_ids=[1, 2],
    )
    _patch_media_client(monkeypatch, FakeMediaClient(by_category={
        "request_photo": [_photo(7)], "completion_photo": [_photo(8)],
    }))

    resp = await client.post(f"{BASE}/{report.id}/autofill")
    assert resp.status_code == 409

    reloaded = (await db_session.execute(
        select(WorkReport).where(WorkReport.id == report.id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert reloaded.before_media_ids == [1]
    assert reloaded.after_media_ids == [2]


@pytest.mark.asyncio
async def test_autofill_pending_skips_published_rows(client: AsyncClient, db_session, monkeypatch):
    """Пакетное автозаполнение фильтруется по статусу: строка published с
    media_synced_at=None (ручной отчёт, опубликованный без autofill) не должна
    попасть под перезапись."""
    _enable(monkeypatch)
    editable = await _mk_report(db_session, "260725-905", status="pending")
    published = await _mk_report(
        db_session, "260725-906", status="published",
        before_media_ids=[1], after_media_ids=[2], locked_media_ids=[1, 2],
    )
    _patch_media_client(monkeypatch, FakeMediaClient(by_category={
        "request_photo": [_photo(7)], "completion_photo": [_photo(8)],
    }))

    resp = await client.post(f"{BASE}/autofill-pending")
    assert resp.status_code == 200
    assert resp.json() == {"processed": 1}

    reloaded = (await db_session.execute(
        select(WorkReport).where(WorkReport.id == published.id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert reloaded.before_media_ids == [1]
    assert reloaded.media_synced_at is None
    assert editable.id != published.id
