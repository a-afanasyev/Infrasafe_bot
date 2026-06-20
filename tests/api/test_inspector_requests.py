"""Тесты структурного адреса заявки: резолвер + applicant/inspector эндпоинты,
approved-гейт, purge-гарды, request-addresses, callcenter (план «Обходчик»).

Покрывает security-ядро: R1/R2 (фиктивная привилегия/обход), R3 (pending-гейт),
R14/R15 (уровни/building-only обходчика), R18 (purge-гард), R36 (callcenter).
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.services.request_address import (
    resolve_request_address_async,
    AddressResolutionError,
)


# ─────────────────────────── фикстуры данных ───────────────────────────


@pytest_asyncio.fixture
async def addr_tree(db_session: AsyncSession):
    """Активный двор → дом → квартира + второй (неактивный) двор/дом."""
    yard = Yard(name="Двор А", is_active=True)
    yard_inactive = Yard(name="Двор Неактивный", is_active=False)
    db_session.add_all([yard, yard_inactive])
    await db_session.flush()

    building = Building(address="ул. Ленина 1", yard_id=yard.id, is_active=True,
                        entrance_count=1, floor_count=9)
    building_in_inactive_yard = Building(address="ул. Мёртвая 2", yard_id=yard_inactive.id,
                                         is_active=True, entrance_count=1, floor_count=5)
    db_session.add_all([building, building_in_inactive_yard])
    await db_session.flush()

    apt = Apartment(building_id=building.id, apartment_number="12", is_active=True)
    db_session.add(apt)
    await db_session.flush()
    await db_session.commit()
    return {
        "yard": yard, "yard_inactive": yard_inactive,
        "building": building, "building_in_inactive_yard": building_in_inactive_yard,
        "apt": apt,
    }


@pytest_asyncio.fixture
async def applicant(db_session: AsyncSession, addr_tree):
    user = User(telegram_id=111, username="appl", first_name="A",
                roles='["applicant"]', status="approved", phone="+700")
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserApartment(user_id=user.id, apartment_id=addr_tree["apt"].id, status="approved"))
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def inspector(db_session: AsyncSession):
    user = User(telegram_id=222, username="insp", first_name="I",
                roles='["inspector"]', status="approved", phone="+701")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def pending_inspector(db_session: AsyncSession):
    user = User(telegram_id=223, username="pinsp", first_name="P",
                roles='["inspector"]', status="pending", phone="+702")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def make_client(db_session_factory):
    """Фабрика AsyncClient с заданным аутентифицированным пользователем."""
    def _make(user: User) -> AsyncClient:
        async def override_get_db():
            async with db_session_factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        async def override_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


def _body(address_type, address_id, **extra):
    b = {"category": "Электрика", "urgency": "low", "description": "Описание проблемы",
         "address_type": address_type, "address_id": address_id}
    b.update(extra)
    return b


# ─────────────────────────── резолвер (async) ──────────────────────────


@pytest.mark.asyncio
async def test_resolver_applicant_own_apartment(db_session, applicant, addr_tree):
    r = await resolve_request_address_async(db_session, applicant.id, "applicant", "apartment", addr_tree["apt"].id)
    assert r.address_type == "apartment"
    assert r.apartment_id == addr_tree["apt"].id
    assert "кв. 12" in r.canonical_address and "Двор А" in r.canonical_address


@pytest.mark.asyncio
async def test_resolver_applicant_own_building_and_yard(db_session, applicant, addr_tree):
    rb = await resolve_request_address_async(db_session, applicant.id, "applicant", "building", addr_tree["building"].id)
    assert rb.building_id == addr_tree["building"].id and rb.apartment_id is None
    ry = await resolve_request_address_async(db_session, applicant.id, "applicant", "yard", addr_tree["yard"].id)
    assert ry.yard_id == addr_tree["yard"].id


@pytest.mark.asyncio
async def test_resolver_foreign_apartment_403(db_session, applicant, addr_tree):
    # Чужая квартира (существует+активна, но не привязана к жителю) → 403.
    other_apt = Apartment(building_id=addr_tree["building"].id, apartment_number="99", is_active=True)
    db_session.add(other_apt)
    await db_session.commit()
    with pytest.raises(AddressResolutionError) as e:
        await resolve_request_address_async(db_session, applicant.id, "applicant", "apartment", other_apt.id)
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_resolver_nonexistent_422(db_session, applicant):
    with pytest.raises(AddressResolutionError) as e:
        await resolve_request_address_async(db_session, applicant.id, "applicant", "apartment", 99999)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_resolver_foreign_yard_403(db_session, applicant, addr_tree):
    # Чужой двор (активен, но нет approved-квартиры жителя и нет UserYard) → 403.
    # Регресс на некоррелированный EXISTS: applicant с квартирой в дворе А не
    # должен резолвить чужой двор Б.
    foreign_yard = Yard(name="Двор Чужой", is_active=True)
    db_session.add(foreign_yard)
    await db_session.commit()
    with pytest.raises(AddressResolutionError) as e:
        await resolve_request_address_async(db_session, applicant.id, "applicant", "yard", foreign_yard.id)
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_resolver_foreign_building_403(db_session, applicant, addr_tree):
    # Чужой дом в чужом дворе → 403 (нет approved-квартиры жителя в нём).
    foreign_yard = Yard(name="Двор Чужой 2", is_active=True)
    db_session.add(foreign_yard)
    await db_session.flush()
    foreign_building = Building(address="ул. Чужая 9", yard_id=foreign_yard.id, is_active=True,
                               entrance_count=1, floor_count=3)
    db_session.add(foreign_building)
    await db_session.commit()
    with pytest.raises(AddressResolutionError) as e:
        await resolve_request_address_async(db_session, applicant.id, "applicant", "building", foreign_building.id)
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_resolver_inspector_building_no_membership(db_session, inspector, addr_tree):
    r = await resolve_request_address_async(db_session, inspector.id, "inspector", "building", addr_tree["building"].id)
    assert r.building_id == addr_tree["building"].id


@pytest.mark.asyncio
async def test_resolver_inspector_building_in_inactive_yard_422(db_session, inspector, addr_tree):
    with pytest.raises(AddressResolutionError) as e:
        await resolve_request_address_async(
            db_session, inspector.id, "inspector", "building", addr_tree["building_in_inactive_yard"].id
        )
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_resolver_inspector_yard_level_forbidden(db_session, inspector, addr_tree):
    # Обходчик — building-only: yard уровень не разрешён.
    with pytest.raises(AddressResolutionError) as e:
        await resolve_request_address_async(db_session, inspector.id, "inspector", "yard", addr_tree["yard"].id)
    assert e.value.status_code == 422


# ─────────────────────────── applicant endpoint ────────────────────────


@pytest.mark.asyncio
async def test_applicant_create_apartment_201(make_client, applicant, addr_tree):
    async with make_client(applicant) as ac:
        r = await ac.post("/api/v2/requests", json=_body("apartment", addr_tree["apt"].id))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["address_type"] == "apartment"
    assert data["apartment_id"] == addr_tree["apt"].id
    assert data["source"] == "twa"


@pytest.mark.asyncio
async def test_applicant_create_foreign_apartment_403(make_client, applicant, addr_tree, db_session):
    other = Apartment(building_id=addr_tree["building"].id, apartment_number="77", is_active=True)
    db_session.add(other)
    await db_session.commit()
    async with make_client(applicant) as ac:
        r = await ac.post("/api/v2/requests", json=_body("apartment", other.id))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_applicant_client_address_ignored(make_client, applicant, addr_tree):
    # Клиентский address/source игнорируются — сервер формирует канон.
    async with make_client(applicant) as ac:
        r = await ac.post("/api/v2/requests",
                          json=_body("apartment", addr_tree["apt"].id, address="ПОДДЕЛКА", source="web"))
    assert r.status_code == 201
    assert r.json()["source"] == "twa"
    assert "ПОДДЕЛКА" not in (r.json()["address"] or "")


# ─────────────────────────── inspector endpoint ────────────────────────


@pytest.mark.asyncio
async def test_inspector_create_building_201(make_client, inspector, addr_tree):
    async with make_client(inspector) as ac:
        r = await ac.post("/api/v2/requests/inspector", json=_body("building", addr_tree["building"].id))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["address_type"] == "building"
    assert data["building_id"] == addr_tree["building"].id
    assert data["source"] == "inspector"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_type", ["yard", "apartment"])
async def test_inspector_non_building_422(make_client, inspector, addr_tree, bad_type):
    aid = addr_tree["yard"].id if bad_type == "yard" else addr_tree["apt"].id
    async with make_client(inspector) as ac:
        r = await ac.post("/api/v2/requests/inspector", json=_body(bad_type, aid))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_inspector_inactive_yard_building_422(make_client, inspector, addr_tree):
    async with make_client(inspector) as ac:
        r = await ac.post("/api/v2/requests/inspector",
                          json=_body("building", addr_tree["building_in_inactive_yard"].id))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_applicant_cannot_use_inspector_endpoint_403(make_client, applicant, addr_tree):
    async with make_client(applicant) as ac:
        r = await ac.post("/api/v2/requests/inspector", json=_body("building", addr_tree["building"].id))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_pending_inspector_blocked_403(make_client, pending_inspector, addr_tree):
    # Approved-гейт: pending со старым токеном не проходит (R3).
    async with make_client(pending_inspector) as ac:
        r = await ac.post("/api/v2/requests/inspector", json=_body("building", addr_tree["building"].id))
    assert r.status_code == 403


# ─────────────────────────── request-addresses ─────────────────────────


@pytest.mark.asyncio
async def test_request_addresses_shape(make_client, applicant, addr_tree):
    async with make_client(applicant) as ac:
        r = await ac.get("/api/v2/profile/request-addresses")
    assert r.status_code == 200, r.text
    data = r.json()
    assert {"yards", "buildings", "apartments"} <= data.keys()
    assert any(a["id"] == addr_tree["apt"].id for a in data["apartments"])
    assert all("yard_id" in b for b in data["buildings"])
    assert all({"building_id", "yard_id"} <= a.keys() for a in data["apartments"])


# ─────────────────────────── purge-гард ────────────────────────────────


@pytest.mark.asyncio
async def test_purge_building_blocked_by_building_level_request(
    make_client, inspector, manager_user, addr_tree, db_session
):
    # Building-level заявка (apartment_id=NULL) должна блокировать purge дома.
    async with make_client(inspector) as ac:
        r = await ac.post("/api/v2/requests/inspector", json=_body("building", addr_tree["building"].id))
    assert r.status_code == 201
    # Soft-delete дома, затем purge (как менеджер) — должен быть заблокирован (409).
    b = addr_tree["building"]
    b.is_active = False
    await db_session.merge(b)
    await db_session.commit()
    async with make_client(manager_user) as ac:
        rp = await ac.delete(f"/api/v2/addresses/buildings/{b.id}/purge")
    assert rp.status_code == 409, rp.text


# ─────────────────────────── callcenter edge-cases ─────────────────────


def _cc_body(**extra):
    b = {"category": "Электрика", "urgency": "low", "description": "Звонок жителя"}
    b.update(extra)
    return b


@pytest.mark.asyncio
async def test_callcenter_apartment_without_user_422(make_client, manager_user, addr_tree):
    async with make_client(manager_user) as ac:
        r = await ac.post("/api/v2/callcenter/requests", json=_cc_body(apartment_id=addr_tree["apt"].id))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_callcenter_nonexistent_user_404(make_client, manager_user):
    async with make_client(manager_user) as ac:
        r = await ac.post("/api/v2/callcenter/requests", json=_cc_body(user_id=999999, address="ул. Х"))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_callcenter_target_not_applicant_422(make_client, manager_user, inspector):
    async with make_client(manager_user) as ac:
        r = await ac.post("/api/v2/callcenter/requests", json=_cc_body(user_id=inspector.id, address="ул. Х"))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_callcenter_no_apartment_empty_address_422(make_client, manager_user):
    async with make_client(manager_user) as ac:
        r = await ac.post("/api/v2/callcenter/requests", json=_cc_body(address="   "))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_callcenter_no_user_owner_is_manager_legacy(make_client, manager_user):
    async with make_client(manager_user) as ac:
        r = await ac.post("/api/v2/callcenter/requests", json=_cc_body(address="ул. Свободная 3"))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["address_type"] == "legacy"
    assert data["address"] == "ул. Свободная 3"


@pytest.mark.asyncio
async def test_callcenter_create_auto_dispatches_group(make_client, manager_user, monkeypatch):
    """FEAT-группы (followup #1): call-center create — канал создания → авто-dispatch
    на группу-специализацию (раньше оставалась «Новая»)."""
    import uk_management_bot.services.dispatch as dispatch_mod
    calls = []

    async def fake_dispatch(request_number, category):
        calls.append((request_number, category))

    monkeypatch.setattr(dispatch_mod, "auto_dispatch_new_request_async", fake_dispatch)
    async with make_client(manager_user) as ac:
        r = await ac.post("/api/v2/callcenter/requests",
                          json=_cc_body(category="Сантехника", address="ул. Тест 1"))
    assert r.status_code == 201, r.text
    # FS-04: категория нормализуется к канон-EN-ключу до dispatch.
    assert calls == [(r.json()["request_number"], "plumbing")]


@pytest.mark.asyncio
async def test_callcenter_with_owned_apartment_canonical(make_client, manager_user, applicant, addr_tree):
    async with make_client(manager_user) as ac:
        r = await ac.post(
            "/api/v2/callcenter/requests",
            json=_cc_body(user_id=applicant.id, apartment_id=addr_tree["apt"].id, address="ПОДДЕЛКА"),
        )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["address_type"] == "apartment"
    assert data["apartment_id"] == addr_tree["apt"].id
    assert "ПОДДЕЛКА" not in (data["address"] or "")


@pytest.mark.asyncio
async def test_callcenter_foreign_apartment_422(make_client, manager_user, applicant, addr_tree, db_session):
    # Квартира не принадлежит target user → 422 (для call-центра — не 403).
    other = Apartment(building_id=addr_tree["building"].id, apartment_number="55", is_active=True)
    db_session.add(other)
    await db_session.commit()
    async with make_client(manager_user) as ac:
        r = await ac.post(
            "/api/v2/callcenter/requests",
            json=_cc_body(user_id=applicant.id, apartment_id=other.id),
        )
    assert r.status_code == 422


# ─────────────────────────── дискриминатор CHECK ───────────────────────


@pytest.mark.asyncio
async def test_discriminator_check_rejects_mismatch(db_session, applicant, addr_tree):
    # address_type='apartment', но apartment_id NULL → нарушение CHECK.
    from sqlalchemy.exc import IntegrityError

    bad = RequestModel(
        request_number="999999-001", user_id=applicant.id, category="Электрика",
        description="x", urgency="low", status="Новая",
        address_type="apartment", apartment_id=None, building_id=None, yard_id=None,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_discriminator_check_allows_legacy_null(db_session, applicant):
    # address_type=NULL (legacy/немигрированная строка) — допустимо (толерантно).
    ok = RequestModel(
        request_number="999999-002", user_id=applicant.id, category="Электрика",
        description="x", urgency="low", status="Новая", address="свободный текст",
        address_type=None,
    )
    db_session.add(ok)
    await db_session.commit()  # не должно бросить


def test_role_layer_inspector_registered():
    from uk_management_bot.utils.constants import USER_ROLES, ROLE_INSPECTOR
    from uk_management_bot.utils.enums import UserRole

    assert ROLE_INSPECTOR == "inspector"
    assert "inspector" in USER_ROLES
    assert UserRole.INSPECTOR.db_value == "inspector"
    assert UserRole.from_db("inspector") is UserRole.INSPECTOR


# ─────────────────── контракт-валидация (code-review follow-ups) ────────


@pytest.mark.asyncio
async def test_callcenter_invalid_category_422(make_client, manager_user):
    # Менеджер не должен заводить заявку с произвольной категорией.
    async with make_client(manager_user) as ac:
        r = await ac.post(
            "/api/v2/callcenter/requests",
            json={"category": "ВыдуманнаяКатегория", "urgency": "low",
                  "description": "x", "address": "ул. Х"},
        )
    assert r.status_code == 422


def test_inspector_schema_matches_resolver_allowed_levels():
    # Инвариант: building-only заперт И в схеме (Literal), И в резолвере. Если
    # кто-то расширит одно без другого — этот тест упадёт.
    from uk_management_bot.api.requests.schemas import CreateInspectorRequestBody
    from uk_management_bot.services.request_address import ROLE_ALLOWED_LEVELS

    schema_levels = set(CreateInspectorRequestBody.model_fields["address_type"].annotation.__args__)
    assert schema_levels == set(ROLE_ALLOWED_LEVELS["inspector"]) == {"building"}
