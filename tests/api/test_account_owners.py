"""Владельцы лицевых счетов (Mening Uyim) → информация менеджеру при проверке жителя.

Импорт заменяет снимок; владелец счёта квартиры виден в очереди модерации и в
карточке жителя. Правила одобрения это не трогает.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models import AccountOwner, Apartment, Building, User, UserApartment, Yard
from uk_management_bot.services.account_owners import OwnersFileError, parse_owners_csv

BASE = "/api/v2/addresses/account-owners"
SAMPLE = (
    '﻿Лицевой счёт;ФИО\n'
    '"1385963552";"Fayziyev Sohib Savriyevich"\n'
    '"2000000001";"Karimova Dilnoza Akmalovna"\n'
    '"битый";"Кто-то"\n'
).encode("utf-8")


def _upload(content: bytes):
    return {"file": ("owners.csv", content, "text/csv")}


# ── парсер ──────────────────────────────────────────────────────────

def test_parse_sample_skips_bad_account():
    owners, skipped = parse_owners_csv(SAMPLE)
    assert owners == {"1385963552": "Fayziyev Sohib Savriyevich",
                      "2000000001": "Karimova Dilnoza Akmalovna"}
    assert skipped == 1


def test_parse_uzbek_headers_and_cp1251():
    owners, _ = parse_owners_csv("Hisob raqami;F.I.SH\n1;Ali Valiyev\n".encode("cp1251", "ignore"))
    assert owners == {"1": "Ali Valiyev"}
    owners, _ = parse_owners_csv("л/с;ФИО\n7;Иванов Иван\n".encode("cp1251"))
    assert owners == {"7": "Иванов Иван"}


def test_parse_rejects_foreign_file():
    with pytest.raises(OwnersFileError):
        parse_owners_csv("Hisob raqami;Balans\n1;100\n".encode())


# ── API ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def flat(db_session: AsyncSession):
    """Квартира со счётом 1385963552, без счёта и со счётом не из выгрузки."""
    yard = Yard(name="Двор-О")
    db_session.add(yard)
    await db_session.flush()
    bld = Building(address="О-1", yard_id=yard.id)
    db_session.add(bld)
    await db_session.flush()
    apts = [
        Apartment(building_id=bld.id, apartment_number="1", account_number="1385963552"),
        Apartment(building_id=bld.id, apartment_number="2"),
        Apartment(building_id=bld.id, apartment_number="3", account_number="9999"),
    ]
    db_session.add_all(apts)
    await db_session.commit()
    return [a.id for a in apts]


async def _applicant(db, tg: int, name: str, apartment_id: int) -> int:
    first, last = name.split(" ", 1)
    u = User(telegram_id=tg, first_name=first, last_name=last, roles='["applicant"]',
             active_role="applicant", status="pending", language="ru")
    db.add(u)
    await db.flush()
    db.add(UserApartment(user_id=u.id, apartment_id=apartment_id, status="pending"))
    await db.commit()
    return u.id


async def test_import_replaces_snapshot_and_counts_linked(
    client: AsyncClient, db_session: AsyncSession, flat
):
    r = await client.post(f"{BASE}/import", files=_upload(SAMPLE))
    assert r.status_code == 200, r.text
    assert r.json() == {"total": 2, "skipped": 1, "linked": 1}

    # Файл балансов вместо владельцев — отказ, прежний снимок цел.
    r = await client.post(f"{BASE}/import", files=_upload("Hisob raqami;Balans\n1;100\n".encode()))
    assert r.status_code == 422
    assert "ФИО" in r.json()["detail"]

    r = await client.post(f"{BASE}/import", files=_upload("л/с;ФИО\n5;Новый Владелец\n".encode()))
    assert r.json() == {"total": 1, "skipped": 0, "linked": 0}
    rows =(await db_session.execute(select(AccountOwner.account_number))).scalars().all()
    assert rows == ["5"]

    summary = (await client.get(f"{BASE}/summary")).json()
    assert summary["total"] == 1 and summary["linked"] == 0 and summary["imported_at"]


async def test_import_requires_addresses_manage(client: AsyncClient, resident_user):
    app.dependency_overrides[get_current_user] = lambda: resident_user
    r = await client.post(f"{BASE}/import", files=_upload(SAMPLE))
    assert r.status_code == 403


async def test_owner_in_moderation_and_resident_card(
    client: AsyncClient, db_session: AsyncSession, flat
):
    await client.post(f"{BASE}/import", files=_upload(SAMPLE))
    tenant = await _applicant(db_session, 7001, "Иванов Пётр", flat[0])
    no_account = await _applicant(db_session, 7004, "Без Счёта", flat[1])
    not_listed = await _applicant(db_session, 7005, "Нет Списка", flat[2])
    expected = {
        tenant: {"status": "found", "account_number": "1385963552",
                 "owner_name": "Fayziyev Sohib Savriyevich"},
        no_account: {"status": "no_account", "account_number": None, "owner_name": None},
        not_listed: {"status": "not_in_list", "account_number": "9999", "owner_name": None},
    }

    queue = (await client.get("/api/v2/addresses/moderation")).json()
    assert {i["user_id"]: i["owner_check"] for i in queue} == expected

    for user_id, check in expected.items():
        card = (await client.get(f"/api/v2/residents/{user_id}")).json()
        assert card["apartments"][0]["owner_check"] == check


async def test_import_audit_details_is_object_without_names(client: AsyncClient, db_session: AsyncSession, flat):
    """A11-CODE-10: details — JSON-объект (как во всём аудите), а не строка с JSON; ФИО не пишем."""
    from uk_management_bot.database.models.audit import AuditLog

    r = await client.post(f"{BASE}/import", files=_upload(SAMPLE))
    assert r.status_code == 200, r.text
    row = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "account_owners_imported"))).scalars().one()
    assert row.details == {"total": 2, "skipped": 1, "linked": 1}
