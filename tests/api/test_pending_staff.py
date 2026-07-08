"""Очередь активации pending-стаффа (менеджеры/исполнители) в дашборде.

Контекст: приглашённый через бота менеджер/исполнитель садится в
`status='pending'`, но веб-очередь верификации (`verification_status`) его не
показывает (менеджер авто-`verified`), а `/approve` запрещает менеджеров. Здесь
проверяем новый staff-flow: фид `GET /employees/pending` (по `status`, вкл.
менеджеров) + активация `PATCH /employees/{id}/activate` (status→approved,
допускает менеджеров) + `decline` (status→blocked), с guard'ами staff-only.
"""
import pytest

from uk_management_bot.database.models.user import User
from uk_management_bot.api.shifts import service

EP = "/api/v2/shifts/employees"


async def _user(db, tg, *, roles, status="pending", verification="pending",
                active_role="applicant", spec=None, deleted_at=None):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="U", last_name=str(tg),
             roles=roles, active_role=active_role, status=status,
             verification_status=verification, specialization=spec,
             deleted_at=deleted_at)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ═══════════════════ Service-level ═══════════════════

@pytest.mark.asyncio
async def test_list_pending_staff_scope(db_session):
    mgr = await _user(db_session, 2001, roles='["applicant", "manager"]', verification="verified")
    exe = await _user(db_session, 2002, roles='["applicant", "executor"]')
    await _user(db_session, 2003, roles='["applicant"]')                       # чистый житель — нет
    await _user(db_session, 2004, roles='["manager"]', status="approved")      # approved — нет
    await _user(db_session, 2005, roles='["executor"]', verification="rejected")  # rejected — нет (Medium-1)
    await _user(db_session, 2006, roles='["manager"]', deleted_at=__import__("datetime").datetime(2026, 7, 8))

    rows = await service.list_pending_staff(db_session)
    ids = {u.telegram_id for u in rows}
    assert ids == {2001, 2002}


@pytest.mark.asyncio
async def test_activate_sets_status_and_promotes_active_role(db_session):
    u = await _user(db_session, 2101, roles='["applicant", "manager"]',
                    active_role="applicant", verification="verified")
    await service.activate_employee(db_session, u)
    assert u.status == "approved"
    assert u.active_role == "manager"  # Medium-3: поднят до стафф-роли


@pytest.mark.asyncio
async def test_activate_verifies_pending_executor(db_session):
    u = await _user(db_session, 2102, roles='["applicant", "executor"]', verification="pending")
    await service.activate_employee(db_session, u)
    assert u.status == "approved"
    assert u.verification_status == "verified"
    assert u.active_role == "executor"


@pytest.mark.asyncio
async def test_decline_blocks(db_session):
    u = await _user(db_session, 2103, roles='["applicant", "manager"]')
    await service.decline_employee(db_session, u)
    assert u.status == "blocked"


@pytest.mark.asyncio
async def test_is_staff(db_session):
    staff = await _user(db_session, 2104, roles='["applicant", "executor"]')
    resident = await _user(db_session, 2105, roles='["applicant"]')
    assert service._is_staff(staff) is True
    assert service._is_staff(resident) is False


# ═══════════════════ HTTP-контракт ═══════════════════

@pytest.mark.asyncio
async def test_get_pending_endpoint_returns_staff_with_roles(client, db_session):
    await _user(db_session, 2201, roles='["applicant", "manager"]', verification="verified")
    await _user(db_session, 2202, roles='["applicant"]')  # житель — не должен попасть
    resp = await client.get(f"{EP}/pending")
    assert resp.status_code == 200  # High-2: /pending резолвится, НЕ падает как /{user_id}
    data = resp.json()
    staff_roles = {"manager", "executor", "inspector"}
    assert len(data) == 1  # только менеджер, житель отфильтрован
    assert set(data[0]["roles"]) & staff_roles  # roles присутствуют и содержат стафф-роль
    assert all(set(u["roles"]) & staff_roles for u in data)  # ни одного чистого жителя


@pytest.mark.asyncio
async def test_activate_manager_endpoint(client, db_session):
    u = await _user(db_session, 2210, roles='["applicant", "manager"]',
                    active_role="applicant", verification="verified")
    resp = await client.patch(f"{EP}/{u.id}/activate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["active_role"] == "manager"


@pytest.mark.asyncio
async def test_activate_applicant_rejected_422(client, db_session):
    u = await _user(db_session, 2211, roles='["applicant"]')
    resp = await client.patch(f"{EP}/{u.id}/activate")
    assert resp.status_code == 422  # High-1: не staff — нельзя активировать по этому flow


@pytest.mark.asyncio
async def test_activate_non_pending_409(client, db_session):
    u = await _user(db_session, 2212, roles='["applicant", "executor"]', status="approved")
    resp = await client.patch(f"{EP}/{u.id}/activate")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_activate_missing_404(client):
    resp = await client.patch(f"{EP}/99999/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_decline_endpoint_blocks(client, db_session):
    u = await _user(db_session, 2213, roles='["applicant", "manager"]', verification="verified")
    resp = await client.patch(f"{EP}/{u.id}/decline")
    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"
