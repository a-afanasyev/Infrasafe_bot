"""Колл-центр: адрес со слов звонящего → варианты из справочника (2026-11-07).

При включённом ИИ менеджер вводит адрес текстом («4g 10 etaj»), ИИ (тот же
классификатор, что у групп) вытаскивает подсказку, матчер предлагает дома
справочника. Адрес заявки по-прежнему только из справочника — выбирает человек.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

import uk_management_bot.services.group_intake.classifier as classifier_mod
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.group_intake.classifier import ClassificationResult, Outcome

URL = "/api/v2/callcenter/address-suggest"


@pytest_asyncio.fixture
async def olmazor(db_session):
    yard = Yard(name="Olmazor City Phase 3", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    b4 = Building(address="Yangi Olmazor, 4G", yard_id=yard.id, is_active=True, entrance_count=1, floor_count=12)
    b14 = Building(address="Yangi Olmazor, 14G", yard_id=yard.id, is_active=True, entrance_count=1, floor_count=12)
    db_session.add_all([b4, b14])
    await db_session.commit()
    return {"yard": yard, "b4": b4, "b14": b14}


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)


def _llm(monkeypatch, result: ClassificationResult):
    async def fake(text, **_kw):
        fake.text = text
        return result
    monkeypatch.setattr(classifier_mod, "classify_message", fake)
    return fake


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_capabilities_follow_ai_flag(client, monkeypatch, enabled):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", enabled)
    r = await client.get("/api/v2/callcenter/capabilities")
    assert r.status_code == 200
    assert r.json() == {"address_suggest": enabled}


@pytest.mark.asyncio
async def test_suggest_off_without_ai(client, monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", False)
    r = await client.post(URL, json={"address_text": "4g 10 etaj"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_ai_hint_finds_directory_buildings(client, monkeypatch, ai_on, olmazor):
    fake = _llm(monkeypatch, ClassificationResult(
        outcome=Outcome.REQUEST, category="repair", urgency="low", confidence=0.9,
        location_scope="building", address_hint="4g"))
    r = await client.post(URL, json={"address_text": "4g 10 etaj", "description": "kafel qorish kerak"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ai_used"] is True
    assert (data["category"], data["urgency"]) == ("repair", "low")
    labels = {o["label"]: o for o in data["options"]}
    # «4g» — подстрока и 4G, и 14G: выбирает человек.
    assert set(labels) == {"Yangi Olmazor, 4G (Olmazor City Phase 3)", "Yangi Olmazor, 14G (Olmazor City Phase 3)"}
    opt = labels["Yangi Olmazor, 4G (Olmazor City Phase 3)"]
    assert (opt["type"], opt["id"], opt["yard_id"]) == ("building", olmazor["b4"].id, olmazor["yard"].id)
    # ИИ получает и проблему, и адрес — как сообщение в группе.
    assert "kafel qorish kerak" in fake.text and "4g 10 etaj" in fake.text


@pytest.mark.asyncio
async def test_without_ai_verdict_falls_back_to_house_numbers(client, monkeypatch, ai_on, olmazor):
    _llm(monkeypatch, ClassificationResult(outcome=Outcome.PROCESSING_ERROR))
    r = await client.post(URL, json={"address_text": "14g, 3 подъезд"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ai_used"] is False and data["category"] is None
    assert [o["id"] for o in data["options"]] == [olmazor["b14"].id]


@pytest.mark.asyncio
async def test_yard_scope_without_yard_match_offers_buildings(client, monkeypatch, ai_on, olmazor):
    _llm(monkeypatch, ClassificationResult(
        outcome=Outcome.REQUEST, category="landscaping", urgency="low", confidence=0.9,
        location_scope="yard", address_hint="14G"))
    r = await client.post(URL, json={"address_text": "у 14G во дворе"})
    assert [o["id"] for o in r.json()["options"]] == [olmazor["b14"].id]


@pytest.mark.asyncio
async def test_address_text_goes_to_notes_address_from_directory(client, db_session, olmazor):
    r = await client.post("/api/v2/callcenter/requests", json={
        "category": "repair", "urgency": "low", "description": "kafel qorish kerak",
        "building_id": olmazor["b4"].id, "address_text": "4g 10 etaj",
    })
    assert r.status_code == 201, r.text
    assert r.json()["address_type"] == "building"
    row = (await db_session.execute(
        select(RequestModel).where(RequestModel.request_number == r.json()["request_number"]))).scalar_one()
    assert row.notes == "Адрес со слов звонящего: 4g 10 etaj"
