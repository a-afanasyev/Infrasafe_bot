"""API «Лифты» (T4): смена статуса с уведомлением жителей и график ТО/освидетельствований.

Отправка сообщений жителям — строго после commit и best-effort: сендер
подменяется, проверяется, что он получил ровно те сообщения, что вернул домен.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.elevators import service as api_service
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
# Дата в далёком будущем: тест не должен «протухнуть», когда календарь дойдёт до неё.
CERT = {"cert_number": "C-2", "cert_valid_until": "2099-01-01",
        "cert_act_url": "https://example.org/act.pdf"}


@pytest.fixture(autouse=True)
def _enable_elevators(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest.fixture
def sent(monkeypatch) -> list:
    """Перехват отправки сообщений жителям: список кортежей (telegram_id, text)."""
    box: list = []

    async def fake_send(messages, **_kwargs) -> int:
        box.extend((m.telegram_id, m.text) for m in messages)
        return len(box)

    monkeypatch.setattr(api_service, "send_plain_messages", fake_send)
    return box


@contextmanager
def _as_user(user: User):
    prev = app.dependency_overrides.get(get_current_user)

    async def override():
        return user

    app.dependency_overrides[get_current_user] = override
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = prev


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """Дом с жителем в подъезде 1 (получатель уведомлений) и квартирой в подъезде 2."""
    resident = User(telegram_id=710001, first_name="R", roles='["applicant"]',
                    active_role="applicant", status="approved", language="ru")
    db_session.add_all([
        Yard(id=1, name="Двор 1", is_active=True),
        Building(id=1, yard_id=1, address="ул. Мира, д. 5", entrance_count=4,
                 floor_count=9, is_active=True),
        Apartment(id=1, building_id=1, apartment_number="1", entrance=1, is_active=True),
        Apartment(id=2, building_id=1, apartment_number="40", entrance=2, is_active=True),
        resident,
    ])
    await db_session.commit()
    await db_session.refresh(resident)
    db_session.add(UserApartment(user_id=resident.id, apartment_id=1, status="approved"))
    await db_session.commit()
    return resident


async def _commissioned(client: AsyncClient, **overrides) -> dict:
    resp = await client.post(BASE, json={**CREATE_BODY, **overrides})
    assert resp.status_code == 201, resp.text
    resp = await client.post(f"{BASE}/{resp.json()['id']}/commission", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _executor(db: AsyncSession) -> User:
    user = User(telegram_id=710002, first_name="E", roles='["executor"]',
                active_role="executor", status="approved")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ── PUT /{id}/status ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_requires_commissioning(client: AsyncClient, seeded, sent):
    created = (await client.post(BASE, json=CREATE_BODY)).json()
    resp = await client.put(f"{BASE}/{created['id']}/status", json={"status": "working"})
    assert resp.status_code == 409, resp.text
    assert sent == []


@pytest.mark.asyncio
async def test_status_noop_and_change_notifies_entrance(client: AsyncClient, seeded, sent):
    detail = await _commissioned(client)
    eid = detail["id"]
    noop = await client.put(f"{BASE}/{eid}/status", json={"status": "working"})
    assert noop.status_code == 200 and noop.json()["changed"] is False
    assert noop.json()["notified_residents"] == 0 and sent == []

    resp = await client.put(f"{BASE}/{eid}/status",
                            json={"status": "under_repair", "reason": "трос"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed"] is True and body["old_status"] == "working"
    assert body["new_status"] == "under_repair" and body["notified_residents"] == 1
    assert len(sent) == 1 and sent[0][0] == 710001 and "ул. Мира, д. 5" in sent[0][1]

    events = (await client.get(f"{BASE}/{eid}/events")).json()
    latest = events[0]
    assert (latest["event_kind"], latest["source"], latest["reason"]) == (
        "status_changed", "manual", "трос")
    assert latest["old_status"] == "working" and latest["new_status"] == "under_repair"
    assert (await client.get(f"{BASE}/{eid}")).json()["current_status"] == "under_repair"


@pytest.mark.asyncio
async def test_status_request_hint_source_and_validation(client: AsyncClient, seeded, sent):
    eid = (await _commissioned(client))["id"]
    resp = await client.put(f"{BASE}/{eid}/status",
                            json={"status": "not_working", "request_number": "260905-001"})
    assert resp.status_code == 200, resp.text
    latest = (await client.get(f"{BASE}/{eid}/events")).json()[0]
    assert latest["source"] == "request_hint" and latest["request_number"] == "260905-001"
    assert sent == []  # для not_working уведомления жителям нет

    assert (await client.put(f"{BASE}/{eid}/status", json={"status": "flying"})).status_code == 422
    resp = await client.put(f"{BASE}/{eid}/status",
                            json={"status": "working", "request_number": "abc"})
    assert resp.status_code == 422
    resp = await client.put(f"{BASE}/{eid}/status", json={"status": "working", "reason": "x" * 501})
    assert resp.status_code == 422
    assert (await client.put(f"{BASE}/999/status", json={"status": "working"})).status_code == 404


@pytest.mark.asyncio
async def test_status_notification_disabled_by_config(client: AsyncClient, seeded, sent):
    eid = (await _commissioned(client))["id"]
    resp = await client.put(f"{BASE}/config",
                            json={"resident_notifications": {"repair_started": False}})
    assert resp.status_code == 200, resp.text
    resp = await client.put(f"{BASE}/{eid}/status", json={"status": "under_repair"})
    assert resp.status_code == 200 and resp.json()["notified_residents"] == 0
    assert sent == []


@pytest.mark.asyncio
async def test_status_saved_even_if_notification_sender_crashes(client: AsyncClient, seeded,
                                                                 monkeypatch, caplog):
    eid = (await _commissioned(client))["id"]

    async def broken(messages, **_kwargs):
        raise RuntimeError("bot api down https://api.telegram.org/botSECRET/sendMessage")

    monkeypatch.setattr(api_service, "send_plain_messages", broken)
    with caplog.at_level("ERROR", logger=api_service.__name__):
        resp = await client.put(f"{BASE}/{eid}/status", json={"status": "under_repair"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed"] is True and resp.json()["notified_residents"] == 0
    assert (await client.get(f"{BASE}/{eid}")).json()["current_status"] == "under_repair"
    assert "RuntimeError" in caplog.text and "SECRET" not in caplog.text


@pytest.mark.asyncio
async def test_executor_can_set_status(client: AsyncClient, seeded, sent, db_session: AsyncSession):
    eid = (await _commissioned(client))["id"]
    executor = await _executor(db_session)
    with _as_user(executor):
        resp = await client.put(f"{BASE}/{eid}/status", json={"status": "maintenance"})
        assert resp.status_code == 200 and resp.json()["changed"] is True


# ── График ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_is_idempotent_and_listed(client: AsyncClient, seeded):
    eid = (await _commissioned(client))["id"]
    body = {"kind": "maintenance", "start": "2026-10-01", "every_months": 1, "count": 3}
    resp = await client.post(f"{BASE}/{eid}/occurrences/generate", json=body)
    assert resp.status_code == 201, resp.text
    assert [o["due_on"] for o in resp.json()] == ["2026-10-01", "2026-11-01", "2026-12-01"]
    again = await client.post(f"{BASE}/{eid}/occurrences/generate", json=body)
    assert again.status_code == 201 and again.json() == []

    listed = (await client.get(f"{BASE}/{eid}/occurrences", params={"state": "planned"})).json()
    assert len(listed) == 3 and all(o["elevator_label"].endswith("лифт 1") for o in listed)
    assert (await client.get(f"{BASE}/{eid}/occurrences", params={"kind": "x"})).status_code == 422
    resp = await client.post(f"{BASE}/{eid}/occurrences/generate", json={**body, "count": 99})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_occurrence_create_reschedule_cancel(client: AsyncClient, seeded):
    eid = (await _commissioned(client))["id"]
    resp = await client.post(f"{BASE}/{eid}/occurrences",
                             json={"kind": "maintenance", "due_on": "2026-10-01"})
    assert resp.status_code == 201, resp.text
    occ = resp.json()
    assert occ["state"] == "planned" and occ["elevator_id"] == eid
    dup = await client.post(f"{BASE}/{eid}/occurrences",
                            json={"kind": "maintenance", "due_on": "2026-10-01"})
    assert dup.status_code == 409

    moved = await client.patch(f"{BASE}/occurrences/{occ['id']}", json={"due_on": "2026-10-15"})
    assert moved.status_code == 200 and moved.json()["due_on"] == "2026-10-15"
    cancelled = await client.post(f"{BASE}/occurrences/{occ['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    frozen = await client.patch(f"{BASE}/occurrences/{occ['id']}", json={"due_on": "2026-11-01"})
    assert frozen.status_code == 409
    assert (await client.patch(f"{BASE}/occurrences/999", json={"due_on": "2026-11-01"})).status_code == 404


@pytest.mark.asyncio
async def test_complete_certification_updates_passport(client: AsyncClient, seeded,
                                                       db_session: AsyncSession):
    eid = (await _commissioned(client))["id"]
    resp = await client.post(f"{BASE}/{eid}/occurrences",
                             json={"kind": "certification", "due_on": "2026-09-10"})
    oid = resp.json()["id"]
    missing = await client.post(f"{BASE}/occurrences/{oid}/complete", json={"comment": "акт"})
    assert missing.status_code == 422, missing.text

    executor = await _executor(db_session)
    with _as_user(executor):
        done = await client.post(f"{BASE}/occurrences/{oid}/complete",
                                 json={"comment": "акт", **CERT})
        assert done.status_code == 200, done.text
        assert done.json()["state"] == "done" and done.json()["done_by_user_id"] == executor.id
        # исполнителю генерация недоступна
        resp = await client.post(f"{BASE}/{eid}/occurrences/generate", json={
            "kind": "maintenance", "start": "2026-10-01", "every_months": 1, "count": 1})
        assert resp.status_code == 403

    detail = (await client.get(f"{BASE}/{eid}")).json()
    assert (detail["cert_number"], detail["cert_valid_until"]) == ("C-2", "2099-01-01")
    assert detail["flags"]["cert_expired"] is False
    kinds = [e["event_kind"] for e in (await client.get(f"{BASE}/{eid}/events")).json()]
    assert kinds[0] == "cert_changed"
    assert (await client.patch(f"{BASE}/occurrences/{oid}", json={"due_on": "2026-12-01"})).status_code == 409
    assert (await client.post(f"{BASE}/occurrences/{oid}/complete", json={})).status_code == 409


@pytest.mark.asyncio
async def test_calendar_across_elevators(client: AsyncClient, seeded):
    first = (await _commissioned(client))["id"]
    second = (await _commissioned(client, entrance_number=2))["id"]
    for eid, day in ((first, "2026-10-01"), (second, "2026-10-05"), (second, "2026-12-05")):
        resp = await client.post(f"{BASE}/{eid}/occurrences", json={"kind": "maintenance", "due_on": day})
        assert resp.status_code == 201

    resp = await client.get(f"{BASE}/occurrences", params={"from": "2026-10-01", "to": "2026-10-31"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [(r["elevator_id"], r["due_on"]) for r in rows] == [(first, "2026-10-01"), (second, "2026-10-05")]
    assert rows[1]["elevator_label"] == "ул. Мира, д. 5, подъезд 2, лифт 1"
    bad = await client.get(f"{BASE}/occurrences", params={"from": "2026-11-01", "to": "2026-10-01"})
    assert bad.status_code == 422
    assert (await client.get(f"{BASE}/occurrences", params={"from": "2026-10-01"})).status_code == 422
