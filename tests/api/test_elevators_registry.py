"""API «Лифты» (T4, /api/v2/elevators): флаг, RBAC, реестр, паспорт, сводка.

Доменная логика покрыта tests/services/test_elevator_service_*.py; здесь —
HTTP-обвязка: единый 404 при выключенном флаге, матрица ролей, маппинг
доменных ошибок на коды, форма ответов и паритет label списка/карточки.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard

BASE = "/api/v2/elevators"
CREATE_BODY = {
    "building_id": 1, "entrance_number": 1, "elevator_number": 1,
    "passport_number": "P-1", "manufacturer": "OTIS", "serial_number": "S-1",
}
LABEL_RU = "ул. Мира, д. 5, подъезд 1, лифт 1"


@pytest.fixture(autouse=True)
def _enable_elevators(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@contextmanager
def _as_user(user: User):
    """Временно подменить текущего пользователя (поверх client-фикстуры)."""
    prev = app.dependency_overrides.get(get_current_user)

    async def override():
        return user

    app.dependency_overrides[get_current_user] = override
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = prev


async def _mk_user(db: AsyncSession, telegram_id: int, roles: str) -> User:
    user = User(telegram_id=telegram_id, first_name="U", last_name=str(telegram_id),
                roles=roles, active_role=roles.strip('[]"'), status="approved")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """Двор, два дома (в первом 4 подъезда), квартира в подъезде 1 дома 1."""
    db_session.add_all([
        Yard(id=1, name="Двор 1", is_active=True),
        Building(id=1, yard_id=1, address="ул. Мира, д. 5", entrance_count=4,
                 floor_count=9, is_active=True),
        Building(id=2, yard_id=1, address="ул. Мира, д. 7", entrance_count=2,
                 floor_count=9, is_active=True),
        Apartment(id=1, building_id=1, apartment_number="1", entrance=1, is_active=True),
    ])
    await db_session.commit()


async def _create(client: AsyncClient, **overrides) -> dict:
    resp = await client.post(BASE, json={**CREATE_BODY, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _commissioned(client: AsyncClient, **overrides) -> dict:
    created = await _create(client, **overrides)
    resp = await client.post(f"{BASE}/{created['id']}/commission", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Флаг ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disabled_flag_gives_404_on_every_path(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    for method, path in [("GET", BASE), ("GET", f"{BASE}/summary"), ("POST", BASE),
                         ("GET", f"{BASE}/1"), ("GET", f"{BASE}/config"),
                         ("GET", f"{BASE}/occurrences")]:
        resp = await client.request(method, path, json=CREATE_BODY if method == "POST" else None)
        assert resp.status_code == 404, f"{method} {path}: {resp.status_code}"


# ── RBAC ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_applicant_forbidden_on_staff_endpoints(client: AsyncClient, seeded,
                                                      db_session: AsyncSession):
    applicant = await _mk_user(db_session, 700001, '["applicant"]')
    with _as_user(applicant):
        for method, path, body in [
            ("GET", BASE, None), ("POST", BASE, CREATE_BODY),
            ("GET", f"{BASE}/summary", None), ("GET", f"{BASE}/1", None),
            ("PUT", f"{BASE}/1/status", {"status": "working"}),
            ("GET", f"{BASE}/config", None), ("GET", f"{BASE}/occurrences", None),
            ("POST", f"{BASE}/requests/bulk-confirm", {"request_numbers": ["260905-001"]}),
        ]:
            resp = await client.request(method, path, json=body)
            assert resp.status_code == 403, f"{method} {path}: {resp.status_code}"


@pytest.mark.asyncio
async def test_executor_reads_but_cannot_manage(client: AsyncClient, seeded,
                                                db_session: AsyncSession):
    created = await _create(client)
    executor = await _mk_user(db_session, 700002, '["executor"]')
    with _as_user(executor):
        assert (await client.get(BASE)).status_code == 200
        assert (await client.get(f"{BASE}/summary")).status_code == 200
        assert (await client.get(f"{BASE}/{created['id']}")).status_code == 200
        for method, path, body in [
            ("POST", BASE, CREATE_BODY),
            ("PATCH", f"{BASE}/{created['id']}", {"model": "X"}),
            ("POST", f"{BASE}/{created['id']}/commission", {}),
            ("POST", f"{BASE}/{created['id']}/archive", {"reason": "x"}),
            ("GET", f"{BASE}/config", None),
            ("POST", f"{BASE}/requests/bulk-confirm", {"request_numbers": ["260905-001"]}),
        ]:
            resp = await client.request(method, path, json=body)
            assert resp.status_code == 403, f"{method} {path}: {resp.status_code}"


# ── Создание / паспорт ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_returns_detail_with_public_code(client: AsyncClient, seeded):
    detail = await _create(client)
    assert detail["is_commissioned"] is False and detail["current_status"] is None
    assert detail["label"] == LABEL_RU
    assert detail["yard_name"] == "Двор 1" and detail["building_address"] == "ул. Мира, д. 5"
    code = detail["public_code"]
    assert 1 <= len(code) <= 32 and not code.isdigit()
    assert detail["flags"] == {"no_contract": True, "cert_expired": True,
                               "maintenance_overdue": False}
    assert detail["apartments_without_entrance_count"] == 0
    assert detail["version"] == 1


@pytest.mark.asyncio
async def test_create_duplicate_place_is_409(client: AsyncClient, seeded):
    await _create(client)
    resp = await client.post(BASE, json=CREATE_BODY)
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_create_validation_errors(client: AsyncClient, seeded):
    assert (await client.post(BASE, json={**CREATE_BODY, "bogus": 1})).status_code == 422
    body = {k: v for k, v in CREATE_BODY.items() if k != "manufacturer"}
    assert (await client.post(BASE, json=body)).status_code == 422
    # подъезд 9 при 4 подъездах дома — доменная валидация → 422
    resp = await client.post(BASE, json={**CREATE_BODY, "entrance_number": 9})
    assert resp.status_code == 422, resp.text
    # неактивный/несуществующий дом
    resp = await client.post(BASE, json={**CREATE_BODY, "building_id": 77})
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_commission_sets_working_and_two_events(client: AsyncClient, seeded):
    detail = await _commissioned(client)
    assert detail["is_commissioned"] is True and detail["current_status"] == "working"
    assert detail["status_since"] is not None and detail["version"] == 2
    events = (await client.get(f"{BASE}/{detail['id']}/events")).json()
    assert sorted(e["event_kind"] for e in events) == ["commissioned", "status_changed"]
    # повтор — 409
    assert (await client.post(f"{BASE}/{detail['id']}/commission", json={})).status_code == 409


@pytest.mark.asyncio
async def test_patch_version_conflict_and_place_freeze(client: AsyncClient, seeded):
    detail = await _commissioned(client)
    eid = detail["id"]
    resp = await client.patch(f"{BASE}/{eid}", json={"model": "Gen2", "expected_version": 1})
    assert resp.status_code == 409, resp.text
    resp = await client.patch(f"{BASE}/{eid}", json={"model": "Gen2", "expected_version": 2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["model"] == "Gen2" and resp.json()["version"] == 3
    # место после ввода в эксплуатацию заморожено
    resp = await client.patch(f"{BASE}/{eid}", json={"entrance_number": 2})
    assert resp.status_code == 409, resp.text
    # patch неизвестного лифта
    assert (await client.patch(f"{BASE}/999", json={"model": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_archive_hides_from_list_unless_included(client: AsyncClient, seeded):
    detail = await _commissioned(client)
    eid = detail["id"]
    assert (await client.post(f"{BASE}/{eid}/archive", json={"reason": ""})).status_code == 422
    resp = await client.post(f"{BASE}/{eid}/archive", json={"reason": "демонтаж"})
    assert resp.status_code == 200 and resp.json()["archived_at"] is not None
    assert (await client.get(BASE)).json()["total"] == 0
    listed = (await client.get(BASE, params={"include_archived": "true"})).json()
    assert listed["total"] == 1 and listed["items"][0]["archived_at"] is not None
    assert (await client.get(f"{BASE}/{eid}")).status_code == 200
    assert (await client.post(f"{BASE}/{eid}/archive", json={"reason": "ещё"})).status_code == 409
    # архивный лифт освобождает место
    assert (await client.post(BASE, json=CREATE_BODY)).status_code == 201


# ── Список / карточка / сводка ───────────────────────────────────────

@pytest.mark.asyncio
async def test_list_and_detail_share_label_and_filters(client: AsyncClient, seeded):
    first = await _commissioned(client)
    await _create(client, entrance_number=2, contract_until="2099-01-01")
    listed = (await client.get(BASE)).json()
    assert listed["total"] == 2
    card = next(c for c in listed["items"] if c["id"] == first["id"])
    assert card["label"] == first["label"] == LABEL_RU
    assert card["availability_30d"] is not None and card["open_requests_count"] == 0
    assert "public_code" not in card

    assert (await client.get(BASE, params={"status": "working"})).json()["total"] == 1
    assert (await client.get(BASE, params={"flag": "no_contract"})).json()["total"] == 1
    assert (await client.get(BASE, params={"building_id": 2})).json()["total"] == 0
    assert (await client.get(BASE, params={"flag": "bogus"})).status_code == 422
    assert (await client.get(BASE, params={"status": "flying"})).status_code == 422

    uz = (await client.get(f"{BASE}/{first['id']}", params={"lang": "uz"})).json()
    assert uz["label"] != LABEL_RU and "1-kirish" in uz["label"]
    assert (await client.get(f"{BASE}/999")).status_code == 404


@pytest.mark.asyncio
async def test_summary_counters(client: AsyncClient, seeded):
    await _commissioned(client)
    await _create(client, entrance_number=2)
    summary = (await client.get(f"{BASE}/summary")).json()
    assert summary["totals"]["total"] == 2
    assert summary["totals"]["by_status"] == {"working": 1}
    assert summary["totals"]["no_contract"] == 2
    assert [y["yard_name"] for y in summary["yards"]] == ["Двор 1"]
    assert summary["requests_without_elevator"] == 0
    assert summary["downtime_threshold_days"]["not_working"] == 7


# ── for-building ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_for_building_applicant_scope(client: AsyncClient, seeded, db_session: AsyncSession):
    working = await _commissioned(client)
    await _create(client, entrance_number=2)  # не введён — в мини-списке отсутствует
    applicant = await _mk_user(db_session, 700003, '["applicant"]')
    with _as_user(applicant):
        assert (await client.get(f"{BASE}/for-building/1")).status_code == 403
    db_session.add(UserApartment(user_id=applicant.id, apartment_id=1, status="approved"))
    await db_session.commit()
    with _as_user(applicant):
        resp = await client.get(f"{BASE}/for-building/1")
        assert resp.status_code == 200, resp.text
        assert [row["id"] for row in resp.json()] == [working["id"]]
        assert resp.json()[0]["label"] == LABEL_RU
        assert resp.json()[0]["current_status"] == "working"
        assert (await client.get(f"{BASE}/for-building/2")).status_code == 403
    executor = await _mk_user(db_session, 700004, '["executor"]')
    with _as_user(executor):
        assert (await client.get(f"{BASE}/for-building/2")).json() == []


@pytest.mark.asyncio
async def test_inspector_sees_for_building_only(client: AsyncClient, seeded,
                                                db_session: AsyncSession):
    working = await _commissioned(client)
    inspector = await _mk_user(db_session, 700005, '["inspector"]')
    with _as_user(inspector):
        resp = await client.get(f"{BASE}/for-building/1")
        assert resp.status_code == 200 and [r["id"] for r in resp.json()] == [working["id"]]
        assert (await client.get(f"{BASE}/for-building/2")).json() == []
        for method, path, body in [
            ("GET", BASE, None), ("GET", f"{BASE}/summary", None),
            ("GET", f"{BASE}/{working['id']}", None),
            ("GET", f"{BASE}/{working['id']}/events", None),
            ("GET", f"{BASE}/occurrences", None),
            ("PUT", f"{BASE}/{working['id']}/status", {"status": "working"}),
            ("POST", BASE, CREATE_BODY), ("GET", f"{BASE}/config", None),
            ("POST", f"{BASE}/requests/bulk-confirm", {"request_numbers": ["260905-001"]}),
        ]:
            resp = await client.request(method, path, json=body)
            assert resp.status_code == 403, f"{method} {path}: {resp.status_code}"


# ── Сортировка реестра ───────────────────────────────────────────────

async def _three_elevators(client: AsyncClient) -> dict[str, int]:
    """Три введённых лифта в доме 1 с разными статусами."""
    ids = {}
    for entrance, (status, name) in enumerate(
        [("working", "ok"), ("not_working", "down"), ("maintenance", "service")], start=1
    ):
        created = await _commissioned(
            client, entrance_number=entrance,
            passport_number=f"P-{name}", serial_number=f"S-{name}",
        )
        ids[name] = created["id"]
        if status != "working":
            resp = await client.put(f"{BASE}/{created['id']}/status", json={"status": status})
            assert resp.status_code == 200, resp.text
    return ids


async def _listed(client: AsyncClient, **params) -> list[int]:
    resp = await client.get(BASE, params=params)
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()["items"]]


@pytest.mark.asyncio
async def test_default_order_is_address_entrance_number(client: AsyncClient, seeded):
    ids = await _three_elevators(client)
    assert await _listed(client) == [ids["ok"], ids["down"], ids["service"]]


@pytest.mark.asyncio
async def test_sort_by_status_puts_broken_first_and_reverses(client: AsyncClient, seeded):
    ids = await _three_elevators(client)
    # «По возрастанию» для статуса — по тяжести: сначала то, что не работает.
    assert await _listed(client, sort="status") == [ids["down"], ids["service"], ids["ok"]]
    assert await _listed(client, sort="status", order="desc") == [
        ids["ok"], ids["service"], ids["down"],
    ]


@pytest.mark.asyncio
async def test_sort_covers_whole_selection_not_just_the_page(client: AsyncClient, seeded):
    """Ключевое свойство: страница — срез уже отсортированной выборки."""
    ids = await _three_elevators(client)
    assert await _listed(client, sort="status", limit=1) == [ids["down"]]
    assert await _listed(client, sort="status", limit=1, offset=2) == [ids["ok"]]


@pytest.mark.asyncio
async def test_sort_by_open_requests_and_since_are_accepted(client: AsyncClient, seeded):
    ids = await _three_elevators(client)
    assert sorted(await _listed(client, sort="open_requests", order="desc")) == sorted(ids.values())
    assert sorted(await _listed(client, sort="status_since")) == sorted(ids.values())


@pytest.mark.asyncio
async def test_unknown_sort_field_is_rejected(client: AsyncClient, seeded):
    assert (await client.get(BASE, params={"sort": "выдумка"})).status_code == 422
    assert (await client.get(BASE, params={"sort": "status", "order": "вверх"})).status_code == 422
