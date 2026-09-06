"""InfraSafe → заявка категории «лифт» (T6, Ф4a-1, Р14): ``alert.uk_elevator_id``.

Итоговая категория (после override) «лифт» + флаг включён → лифт обязан
резолвиться (активен, введён, дом = дом ``external_id``); иначе 422 и запись
``webhook_inbox`` с ``outcome="rejected"``. Валидный → заявка с ``elevator_id``
и ``elevator_operational=False`` (InfraSafe сообщает о неисправности).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.webhook_inbox import WebhookInbox
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.elevator_service import generate_public_code
from uk_management_bot.services.reconciliation import _expected_external_id

URL = "/api/v2/webhooks/infrasafe/alert"
TEST_SECRET = "test_uk_webhook_secret_primary"


def _alert_body(event_id: str, external_id: str, *, uk_category_override: str | None = "elevator",
                uk_elevator_id: int | None = None) -> bytes:
    alert = {"external_id": external_id, "type": "ELEVATOR_FAULT",
             "severity": "CRITICAL", "message": "Лифт остановился между этажами"}
    if uk_category_override is not None:
        alert["uk_category_override"] = uk_category_override
    if uk_elevator_id is not None:
        alert["uk_elevator_id"] = uk_elevator_id
    return json.dumps({"event_id": event_id, "event": "alert.created",
                       "timestamp": "2026-09-05T12:00:00Z", "alert": alert}).encode()


def _signed(raw: bytes, ip: str = "203.0.114.9") -> dict:
    ts = int(time.time())
    sig = hmac.new(TEST_SECRET.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return {"x-webhook-signature": f"t={ts},v1={sig}", "X-Real-IP": ip}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET_NEXT", "")
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)

    async def _no_replay(event_id: str) -> bool:
        return False
    monkeypatch.setattr("uk_management_bot.services.inbound_alert.is_replay", _no_replay)


@pytest_asyncio.fixture
async def webhook_client(db_session_factory):
    async def override_get_db():
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _elevator(building_id: int, *, number: int, commissioned: bool = True) -> Elevator:
    return Elevator(
        building_id=building_id, entrance_number=1, elevator_number=number,
        passport_number=f"P-{number}", manufacturer="KONE", serial_number=f"S-{number}",
        public_code=generate_public_code(), is_commissioned=commissioned,
        commissioned_at=date(2020, 1, 1) if commissioned else None,
        current_status="working" if commissioned else None,
    )


@pytest_asyncio.fixture
async def world(db_session):
    """Двор, дом + чужой дом, системный пользователь InfraSafe, три лифта."""
    yard = Yard(name="Тестовый двор", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    building = Building(address="ул. Тестовая, 1", yard_id=yard.id, is_active=True)
    other = Building(address="ул. Чужая, 2", yard_id=yard.id, is_active=True)
    sysuser = User(telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID, first_name="InfraSafe",
                   roles='["manager"]', active_role="manager", status="approved")
    db_session.add_all([building, other, sysuser])
    await db_session.flush()
    ok = _elevator(building.id, number=1)
    raw = _elevator(building.id, number=2, commissioned=False)
    foreign = _elevator(other.id, number=1)
    repairing = _elevator(building.id, number=3)
    repairing.current_status = "under_repair"
    db_session.add_all([ok, raw, foreign, repairing])
    await db_session.commit()
    return {"building": building, "ok": ok, "raw": raw, "foreign": foreign,
            "repairing": repairing}


async def _inbox(db_session, event_id: str) -> WebhookInbox | None:
    return await db_session.scalar(select(WebhookInbox).where(WebhookInbox.event_id == event_id))


async def _requests(db_session) -> list[Request]:
    return list((await db_session.execute(select(Request))).scalars().all())


@pytest.mark.asyncio
async def test_elevator_category_without_uk_elevator_id_422_and_inbox_rejected(
    webhook_client, world, db_session,
):
    raw = _alert_body("evt-lift-missing", _expected_external_id(world["building"].id))
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 422, r.text
    assert "uk_elevator_id" in r.json()["detail"]

    row = await _inbox(db_session, "evt-lift-missing")
    assert row is not None and row.outcome == "rejected"
    assert row.request_number is None and row.error and "elevator" in row.error
    assert await _requests(db_session) == []


@pytest.mark.asyncio
async def test_elevator_of_other_building_422(webhook_client, world, db_session):
    raw = _alert_body("evt-lift-foreign", _expected_external_id(world["building"].id),
                      uk_elevator_id=world["foreign"].id)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 422, r.text
    row = await _inbox(db_session, "evt-lift-foreign")
    assert row is not None and row.outcome == "rejected" and "другому дому" in row.error
    assert await _requests(db_session) == []


@pytest.mark.asyncio
async def test_uncommissioned_elevator_422(webhook_client, world, db_session):
    raw = _alert_body("evt-lift-raw", _expected_external_id(world["building"].id),
                      uk_elevator_id=world["raw"].id)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 422, r.text
    assert (await _inbox(db_session, "evt-lift-raw")).outcome == "rejected"


@pytest.mark.asyncio
async def test_valid_elevator_creates_bound_request(webhook_client, world, db_session):
    raw = _alert_body("evt-lift-ok", _expected_external_id(world["building"].id),
                      uk_elevator_id=world["ok"].id)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 202, r.text
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.category == "elevator"
    assert req.elevator_id == world["ok"].id
    assert req.elevator_operational is False
    assert req.building_id == world["building"].id
    assert (await _inbox(db_session, "evt-lift-ok")).outcome == "accepted"


@pytest.mark.asyncio
async def test_ru_label_override_is_elevator_category_too(webhook_client, world, db_session):
    """Override хранится как прислали («Лифт») — Р11 применяется по канон-ключу."""
    raw = _alert_body("evt-lift-ru", _expected_external_id(world["building"].id),
                      uk_category_override="Лифт")
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 422, r.text
    assert (await _inbox(db_session, "evt-lift-ru")).outcome == "rejected"


@pytest.mark.asyncio
async def test_other_category_without_field_unchanged(webhook_client, world, db_session):
    raw = _alert_body("evt-plain", _expected_external_id(world["building"].id),
                      uk_category_override=None)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 202, r.text
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.elevator_id is None and req.elevator_operational is None


@pytest.mark.asyncio
async def test_flag_off_elevator_category_behaves_as_before(webhook_client, world, db_session,
                                                            monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    raw = _alert_body("evt-lift-off", _expected_external_id(world["building"].id),
                      uk_elevator_id=world["raw"].id)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 202, r.text
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.category == "elevator"
    assert req.elevator_id is None and req.elevator_operational is None


@pytest.mark.asyncio
async def test_alert_on_elevator_under_works_still_creates_request(
    webhook_client, world, db_session,
):
    """Р18: машинный алерт терять нельзя — по лифту в ремонте заявка создаётся."""
    raw = _alert_body("evt-lift-under-works", _expected_external_id(world["building"].id),
                      uk_elevator_id=world["repairing"].id)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw))
    assert r.status_code == 202, r.text

    requests = await _requests(db_session)
    assert len(requests) == 1
    assert requests[0].elevator_id == world["repairing"].id
    assert requests[0].elevator_operational is False
