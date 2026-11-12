"""Дашборд: специализации сотрудника и просмотр удалённых.

Специализацию раньше можно было задать только в инвайте и в боте: исполнитель,
получивший роль галочкой в блоке «Роли», оставался без специализации и не
попадал в подбор. Удалённые (мягко, из веба) не были видны нигде в панели.
"""
import datetime
import json

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User

EP = "/api/v2/shifts/employees"


async def _user(db, tg, *, roles, status="approved", spec=None, **extra):
    u = User(telegram_id=tg, first_name="U", last_name=str(tg), roles=roles, active_role="executor",
             status=status, specialization=spec, **extra)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ── специализации ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_sets_executor_specializations(client, db_session, manager_user):
    u = await _user(db_session, 5001, roles='["executor"]')
    r = await client.put(f"{EP}/{u.id}/specializations", json={"specializations": ["plumber", "electrician"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": u.id, "specialization": ["electrician", "plumber"]}
    await db_session.refresh(u)
    assert sorted(json.loads(u.specialization)) == ["electrician", "plumber"]
    audit = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "specializations_updated"))).scalar_one()
    assert audit.user_id == manager_user.id
    details = json.loads(audit.details)
    assert (details["target_user_id"], details["old"], details["new"]) == (u.id, [], ["electrician", "plumber"])
    # карточка отдаёт новое значение
    card = await client.get(f"{EP}/{u.id}")
    assert sorted(card.json()["specialization"]) == ["electrician", "plumber"]


@pytest.mark.asyncio
async def test_empty_list_clears_specializations(client, db_session):
    u = await _user(db_session, 5002, roles='["executor"]', spec='["plumber"]')
    r = await client.put(f"{EP}/{u.id}/specializations", json={"specializations": []})
    assert r.status_code == 200 and r.json()["specialization"] == []
    await db_session.refresh(u)
    assert u.specialization is None


@pytest.mark.asyncio
async def test_specializations_guards(client, db_session):
    executor = await _user(db_session, 5003, roles='["executor"]')
    manager = await _user(db_session, 5004, roles='["manager"]')
    deleted = await _user(db_session, 5005, roles='["executor"]', status="deleted",
                          deleted_at=datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc))
    body = {"specializations": ["plumber"]}
    assert (await client.put(f"{EP}/{executor.id}/specializations",
                             json={"specializations": ["wizard"]})).status_code == 422  # неизвестная
    assert (await client.put(f"{EP}/{manager.id}/specializations", json=body)).status_code == 422  # не исполнитель
    assert (await client.put(f"{EP}/{deleted.id}/specializations", json=body)).status_code == 409
    assert (await client.put(f"{EP}/999999/specializations", json=body)).status_code == 404


# ── удалённые ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deleted_staff_are_listed_with_who_when_why(client, db_session, manager_user):
    when = datetime.datetime(2026, 11, 2, 10, 0, tzinfo=datetime.timezone.utc)
    gone = await _user(db_session, 5101, roles='["executor"]', status="deleted", deleted_at=when,
                       deleted_by=manager_user.id, deletion_reason="уволен")
    await _user(db_session, 5102, roles='["executor"]')                                   # работает — нет
    await _user(db_session, 5103, roles='["applicant"]', status="deleted", deleted_at=when)  # житель — нет
    r = await client.get(f"{EP}/deleted")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["id"] for x in rows] == [gone.id]
    row = rows[0]
    assert (row["full_name"], row["roles"], row["deletion_reason"]) == ("U 5101", ["executor"], "уволен")
    assert row["deleted_by_name"] == "Test Manager"
    assert row["deleted_at"].startswith("2026-11-02T10:00")
    # в обычном списке удалённого по-прежнему нет
    assert gone.id not in [x["id"] for x in (await client.get(EP)).json()]
