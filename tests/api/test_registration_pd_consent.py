"""Регистрация жителя требует согласия на обработку персональных данных.

Без флажка заявка не принимается (422); с флажком сервер сам ставит время и
версию текста и пишет запись в журнал — это доказательство согласия, которое
оператор обязан хранить (ЗРУ-547, ст. 31).
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.pd_consent import PD_CONSENT_VERSION


def _bearer(tid: int) -> dict:
    from uk_management_bot.api.registration.tickets import create_registration_ticket
    return {"Authorization": f"Bearer {create_registration_ticket(tid)}"}


@pytest.fixture(autouse=True)
def _mock_notify(monkeypatch):
    monkeypatch.setattr(
        "uk_management_bot.api.registration.router.notify_managers_new_registration", AsyncMock())
    monkeypatch.setattr(
        "uk_management_bot.api.registration.router.offer_document_upload", AsyncMock())


async def _seed(db, telegram_id: int) -> int:
    db.add(User(telegram_id=telegram_id, status="pending", phone="+998901234567"))
    yard = Yard(name=f"Двор-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(yard)
    await db.flush()
    building = Building(address="ул. Ленина 1", yard_id=yard.id, is_active=True)
    db.add(building)
    await db.flush()
    apartment = Apartment(apartment_number="12", building_id=building.id, is_active=True)
    db.add(apartment)
    await db.commit()
    return apartment.id


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"pd_consent": False}])
async def test_registration_without_consent_is_rejected(client, db_session, extra):
    tid = 880001
    apartment_id = await _seed(db_session, tid)

    resp = await client.post(
        "/api/v2/registration/applicant", headers=_bearer(tid),
        json={"full_name": "Иван Иванов", "apartment_id": apartment_id, **extra})

    assert resp.status_code == 422
    user = (await db_session.execute(select(User).where(User.telegram_id == tid))).scalar_one()
    assert user.pd_consent_at is None


@pytest.mark.asyncio
async def test_registration_with_consent_records_evidence(client, db_session):
    tid = 880002
    apartment_id = await _seed(db_session, tid)

    resp = await client.post(
        "/api/v2/registration/applicant", headers=_bearer(tid),
        json={"full_name": "Иван Иванов", "apartment_id": apartment_id, "pd_consent": True})

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    user = (await db_session.execute(select(User).where(User.telegram_id == tid))).scalar_one()
    assert user.pd_consent_at is not None
    assert user.pd_consent_version == PD_CONSENT_VERSION
    log = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "pd_consent_given"))).scalar_one()
    assert log.user_id == user.id
    assert log.details == {"version": PD_CONSENT_VERSION, "source": "registration"}


@pytest.mark.asyncio
async def test_repeated_submission_keeps_single_consent_record(client, db_session):
    tid = 880003
    apartment_id = await _seed(db_session, tid)
    payload = {"full_name": "Иван Иванов", "apartment_id": apartment_id, "pd_consent": True}

    first = await client.post("/api/v2/registration/applicant", headers=_bearer(tid), json=payload)
    second = await client.post("/api/v2/registration/applicant", headers=_bearer(tid), json=payload)

    assert (first.status_code, second.status_code) == (200, 200), second.text
    logs = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "pd_consent_given"))).scalars().all()
    assert len(logs) == 1
