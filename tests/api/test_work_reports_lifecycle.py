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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uk_management_bot.api.work_reports.router as work_reports_router
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
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
    assert set(body.keys()) == {"sync", "revoked", "reconcile"}
    assert body["reconcile"] is None


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
    assert set(body.keys()) == {"unstuck_publishing", "orphaned_locks_released", "missing_locks_relocked"}


@pytest.mark.asyncio
async def test_reconcile_503_without_media_client(client: AsyncClient, monkeypatch):
    _enable(monkeypatch)
    _patch_media_client(monkeypatch, None)

    resp = await client.post(f"{BASE}/reconcile")
    assert resp.status_code == 503
