"""Диспетчер: приём заявки по телефону (экран /twa/dispatch).

Роль видит ровно то, что нужно для звонка: дворы/дома, номера квартир без
данных жильцов, квартиры найденного жителя, создание заявки и проверку
заявки перед отправкой (ИИ читает описание, решения — правила).
"""
import pytest
import pytest_asyncio

import uk_management_bot.services.group_intake.classifier as classifier_mod
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.group_intake.classifier import ClassificationResult, Outcome

CHECK = "/api/v2/callcenter/check"


@pytest_asyncio.fixture
async def olmazor(db_session, resident_user):
    yard = Yard(name="Olmazor City Phase 3", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    b4 = Building(address="Yangi Olmazor, 4G", yard_id=yard.id, is_active=True, entrance_count=1, floor_count=12)
    b14 = Building(address="Yangi Olmazor, 14G", yard_id=yard.id, is_active=True, entrance_count=1, floor_count=12)
    db_session.add_all([b4, b14])
    await db_session.flush()
    a12 = Apartment(building_id=b4.id, apartment_number="12", is_active=True)
    a7 = Apartment(building_id=b4.id, apartment_number="7", is_active=True)
    closed = Apartment(building_id=b4.id, apartment_number="99", is_active=False)
    db_session.add_all([a12, a7, closed])
    await db_session.flush()
    db_session.add(UserApartment(user_id=resident_user.id, apartment_id=a12.id, status="approved"))
    await db_session.commit()
    return {"yard": yard, "b4": b4, "b14": b14, "a12": a12, "a7": a7}


@pytest_asyncio.fixture
async def dispatcher(client, db_session):
    """Клиент под человеком только с ролью «Диспетчер»."""
    user = User(telegram_id=777001, first_name="Dina", roles='["dispatcher"]',
                active_role="dispatcher", status="approved")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    async def _current():
        return user

    app.dependency_overrides[get_current_user] = _current
    return client


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)


def _llm(monkeypatch, **fields):
    result = ClassificationResult(**{"outcome": Outcome.REQUEST, "confidence": 0.9, **fields})

    async def fake(text, **_kw):
        fake.text = text
        return result

    monkeypatch.setattr(classifier_mod, "classify_message", fake)
    return fake


def _body(olmazor, **over):
    return {"category": "plumbing", "urgency": "low", "description": "течёт труба в ванной",
            "building_id": olmazor["b4"].id, **over}


# ── права и чтение справочника ───────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_creates_request_and_reads_directory(dispatcher, olmazor):
    yards = await dispatcher.get("/api/v2/addresses/yards")
    assert yards.status_code == 200 and [y["id"] for y in yards.json()] == [olmazor["yard"].id]
    r = await dispatcher.post("/api/v2/callcenter/requests", json={
        **_body(olmazor), "caller_name": "Aziz", "caller_phone": "+998901112233", "acceptance_mode": "manager"})
    assert r.status_code == 201, r.text
    assert r.json()["address_type"] == "building"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v2/requests/kanban",
    "/api/v2/residents",
    "/api/v2/addresses/buildings/1/apartments",
])
async def test_dispatcher_sees_nothing_beyond_call_intake(dispatcher, path):
    assert (await dispatcher.get(path)).status_code == 403


@pytest.mark.asyncio
async def test_resident_cannot_use_call_intake(dispatcher, olmazor, resident_user):
    async def _resident():
        return resident_user

    app.dependency_overrides[get_current_user] = _resident
    for path in (f"/api/v2/callcenter/buildings/{olmazor['b4'].id}/apartments",
                 f"/api/v2/callcenter/residents/{resident_user.id}/apartments"):
        assert (await dispatcher.get(path)).status_code == 403, path
    assert (await dispatcher.post(CHECK, json=_body(olmazor))).status_code == 403


@pytest.mark.asyncio
async def test_building_apartments_are_numbers_only(dispatcher, olmazor):
    r = await dispatcher.get(f"/api/v2/callcenter/buildings/{olmazor['b4'].id}/apartments")
    assert r.status_code == 200, r.text
    # Только активные, по номеру как по числу; данных жильцов в ответе нет.
    assert r.json() == [{"id": olmazor["a7"].id, "number": "7"}, {"id": olmazor["a12"].id, "number": "12"}]
    assert (await dispatcher.get("/api/v2/callcenter/buildings/999999/apartments")).status_code == 404


@pytest.mark.asyncio
async def test_resident_apartments_for_one_tap_address(dispatcher, olmazor, resident_user):
    r = await dispatcher.get(f"/api/v2/callcenter/residents/{resident_user.id}/apartments")
    assert r.status_code == 200, r.text
    assert r.json() == [{"id": olmazor["a12"].id, "label": "Yangi Olmazor, 4G, кв. 12 (Olmazor City Phase 3)",
                         "building_id": olmazor["b4"].id}]


# ── проверка заявки перед отправкой ──────────────────────────────────

@pytest.mark.asyncio
async def test_check_is_off_without_ai(dispatcher, olmazor, monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", False)
    assert (await dispatcher.post(CHECK, json=_body(olmazor))).status_code == 404


@pytest.mark.asyncio
async def test_check_passes_a_consistent_request(dispatcher, olmazor, ai_on, monkeypatch):
    fake = _llm(monkeypatch, category="plumbing", urgency="low", location_scope="building", address_hint=None)
    r = await dispatcher.post(CHECK, json=_body(olmazor))
    assert r.status_code == 200, r.text
    assert r.json() == {"ai_used": True, "issues": []}
    assert "течёт труба" in fake.text


@pytest.mark.asyncio
async def test_check_flags_category_urgency_and_address(dispatcher, olmazor, ai_on, monkeypatch):
    _llm(monkeypatch, category="plumbing", urgency="high", location_scope="building", address_hint="14G")
    r = await dispatcher.post(CHECK, json=_body(olmazor, category="electricity", description="потоп в подвале 14G"))
    assert r.status_code == 200, r.text
    issues = {i["code"]: i for i in r.json()["issues"]}
    assert set(issues) == {"category_mismatch", "urgency_low", "address_mismatch"}
    assert (issues["category_mismatch"]["field"], issues["category_mismatch"]["suggestion"]) == ("category", "plumbing")
    assert (issues["urgency_low"]["field"], issues["urgency_low"]["suggestion"]) == ("urgency", "high")
    option = issues["address_mismatch"]["options"][0]
    assert (option["type"], option["id"], option["yard_id"]) == ("building", olmazor["b14"].id, olmazor["yard"].id)


@pytest.mark.asyncio
async def test_check_accepts_chosen_address_among_matches(dispatcher, olmazor, ai_on, monkeypatch):
    # «4g» — подстрока и 4G, и 14G: выбранный 4G среди вариантов → замечания нет.
    _llm(monkeypatch, category="plumbing", urgency="low", location_scope="building", address_hint="4g")
    r = await dispatcher.post(CHECK, json=_body(olmazor, apartment_id=olmazor["a12"].id, building_id=None))
    assert r.json()["issues"] == []


@pytest.mark.asyncio
async def test_check_asks_for_apartment_when_problem_is_inside(dispatcher, olmazor, ai_on, monkeypatch):
    _llm(monkeypatch, category="plumbing", urgency="low", location_scope="apartment", address_hint=None)
    r = await dispatcher.post(CHECK, json=_body(olmazor))
    assert [(i["code"], i["field"]) for i in r.json()["issues"]] == [("apartment_expected", "address")]


@pytest.mark.asyncio
async def test_check_does_not_nag_when_ai_is_unsure_or_urgency_is_higher(dispatcher, olmazor, ai_on, monkeypatch):
    _llm(monkeypatch, category="electricity", urgency="low", confidence=0.3,
         location_scope="unknown", address_hint=None)
    r = await dispatcher.post(CHECK, json=_body(olmazor, urgency="critical"))
    assert r.json()["issues"] == []


@pytest.mark.asyncio
async def test_check_flags_unclear_description(dispatcher, olmazor, ai_on, monkeypatch):
    _llm(monkeypatch, outcome=Outcome.NOT_REQUEST)
    r = await dispatcher.post(CHECK, json=_body(olmazor, description="позвонили"))
    assert r.json() == {"ai_used": True, "issues": [
        {"field": "description", "code": "description_unclear", "suggestion": None, "options": []}]}


@pytest.mark.asyncio
async def test_check_never_blocks_when_model_fails(dispatcher, olmazor, ai_on, monkeypatch):
    _llm(monkeypatch, outcome=Outcome.PROCESSING_ERROR)
    r = await dispatcher.post(CHECK, json=_body(olmazor, category="electricity"))
    assert r.status_code == 200 and r.json() == {"ai_used": False, "issues": []}


# ── находки ревью безопасности/кода (2026-11-11) ─────────────────────

SEARCH = "/api/v2/callcenter/search-resident"


@pytest.mark.asyncio
async def test_dispatcher_searches_residents_by_phone_only(dispatcher, resident_user):
    """Диспетчер ищет звонящего по номеру; перебор справочника жителей по
    паре букв — только у того, кто и так ведёт жителей (менеджер)."""
    by_phone = await dispatcher.get(SEARCH, params={"q": "001234567"})
    assert by_phone.status_code == 200 and [r["id"] for r in by_phone.json()] == [resident_user.id]
    assert (await dispatcher.get(SEARCH, params={"q": "Res"})).status_code == 422
    assert (await dispatcher.get(SEARCH, params={"q": "0012"})).status_code == 422


@pytest.mark.asyncio
async def test_phone_search_ignores_separators_in_stored_number(dispatcher, db_session, resident_user):
    """Номер в базе бывает записан с пробелами и дефисами (найдено живой
    проверкой): звонящий обязан находиться по цифрам."""
    resident_user.phone = "+998 (90) 000-00-01"
    await db_session.commit()
    r = await dispatcher.get(SEARCH, params={"q": "900000001"})
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [resident_user.id]


@pytest.mark.asyncio
async def test_manager_still_searches_residents_by_name(client, resident_user):
    r = await client.get(SEARCH, params={"q": "Res"})
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [resident_user.id]


@pytest.mark.asyncio
async def test_resident_apartments_only_for_approved_residents(dispatcher, olmazor, manager_user):
    """Не житель (сотрудник, чужой id) — 404: по id нельзя узнать, кто где живёт."""
    assert (await dispatcher.get(f"/api/v2/callcenter/residents/{manager_user.id}/apartments")).status_code == 404
    assert (await dispatcher.get("/api/v2/callcenter/residents/999999/apartments")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("phone", ["<b>998</b>", "звоните", "+99890111223344556677889900"])
async def test_caller_phone_is_digits_only(dispatcher, olmazor, phone):
    r = await dispatcher.post("/api/v2/callcenter/requests", json={**_body(olmazor), "caller_phone": phone})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_dispatcher_sees_elevators_of_any_building(db_session, olmazor):
    """Шаг «Лифт»: право `elevators.lookup` выдано роли — проверка дома обязана его учитывать."""
    from uk_management_bot.api.elevators import service as elevators

    user = User(telegram_id=777002, first_name="Dina", roles='["dispatcher"]',
                active_role="dispatcher", status="approved")
    db_session.add(user)
    await db_session.commit()
    assert await elevators.can_view_building(db_session, user, olmazor["b4"].id) is True
