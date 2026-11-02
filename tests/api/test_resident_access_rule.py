"""Правило доступа жителя (approval_rules, решение владельца 2026-11-03) на ВСЕХ путях.

Раздел «Жители» и бот покрыты своими тестами; здесь — сама таблица правила и
соседний раздел «Сотрудники», чьи approve/unblock сек-ревью нашло открытыми:
житель через них получал verified/approved без документа и телефона.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import DocumentType, UserDocument
from uk_management_bot.services.residents.approval_rules import (
    account_refusal, verification_refusal,
)


@pytest.mark.parametrize("roles,phone,verification,expected", [
    ('["applicant"]', None, "verified", "phone_required"),
    ('["applicant"]', "+998901234567", "pending", "verification_required"),
    ('["applicant"]', "+998901234567", "verified", None),
    ('["applicant", "resource_meter_entry"]', None, "verified", "phone_required"),
    (None, None, "pending", "phone_required"),         # пустые roles — тоже житель
    ("[]", "+998901234567", "pending", "verification_required"),
    ('["executor"]', None, "pending", None),           # стафф правилом не затрагивается
    ('["applicant", "executor"]', None, "pending", None),
])
def test_account_refusal_table(roles, phone, verification, expected):
    user = SimpleNamespace(roles=roles, phone=phone, verification_status=verification)
    assert account_refusal(user) == expected


@pytest.mark.parametrize("has_doc,in_person,expected", [
    (False, False, "property_document_required"),
    (True, False, None),
    (False, True, None),
])
def test_verification_refusal_table(has_doc, in_person, expected):
    assert verification_refusal(has_property_doc=has_doc, in_person=in_person) == expected


async def _resident(db, tg, *, status="pending", phone=None, verification="pending"):
    u = User(telegram_id=tg, first_name="Ж", roles='["applicant"]', active_role="applicant",
             status=status, phone=phone, verification_status=verification, language="ru")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_employees_approve_refuses_resident_without_property_document(client, db_session):
    resident = await _resident(db_session, 8801)
    rid = resident.id
    db_session.add(UserDocument(user_id=rid, document_type=DocumentType.PASSPORT,
                                file_id="f", file_name="p.jpg", file_size=1))
    await db_session.commit()

    r = await client.patch(f"/api/v2/shifts/employees/{rid}/approve")

    assert r.status_code == 409
    assert r.headers["X-Error-Code"] == "property_document_required"
    db_session.expire_all()
    assert (await db_session.execute(
        select(User.verification_status).where(User.id == rid))).scalar_one() == "pending"


@pytest.mark.asyncio
async def test_employees_approve_accepts_resident_with_property_document(client, db_session):
    resident = await _resident(db_session, 8802)
    db_session.add(UserDocument(user_id=resident.id, document_type=DocumentType.RENTAL_AGREEMENT,
                                file_id="f", file_name="p.jpg", file_size=1))
    await db_session.commit()

    r = await client.patch(f"/api/v2/shifts/employees/{resident.id}/approve")

    assert r.status_code == 200, r.text
    assert r.json()["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_employees_unblock_returns_incomplete_resident_to_pending(client, db_session):
    resident = await _resident(db_session, 8803, status="blocked")

    r = await client.patch(f"/api/v2/shifts/employees/{resident.id}/unblock")

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_employees_unblock_staff_still_approved(client, db_session):
    staff = User(telegram_id=8804, first_name="С", roles='["executor"]', active_role="executor",
                 status="blocked", verification_status="pending", language="ru")
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)

    r = await client.patch(f"/api/v2/shifts/employees/{staff.id}/unblock")

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
