"""Простой режим исполнителя: менеджер включает/выключает флаг сотруднику.

`PATCH /api/v2/shifts/employees/{id}/simple-mode {enabled}` — только manager;
включить можно только исполнителю, выключить — всегда (снятие флага не должно
застревать, если роль исполнителя у человека уже забрали). Флаг виден в
карточке и списке сотрудников.
"""
import pytest

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.user import User

EP = "/api/v2/shifts/employees"


async def _user(db, tg, *, roles='["executor"]', simple_mode=False):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="U", last_name=str(tg),
             roles=roles, active_role="executor", status="approved",
             verification_status="verified", simple_mode=simple_mode)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_manager_enables_simple_mode_for_executor(client, db_session):
    u = await _user(db_session, 3001)

    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": True})

    assert resp.status_code == 200
    assert resp.json() == {"id": u.id, "simple_mode": True}
    await db_session.refresh(u)
    assert u.simple_mode is True


@pytest.mark.asyncio
async def test_manager_disables_simple_mode(client, db_session):
    u = await _user(db_session, 3002, simple_mode=True)

    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": False})

    assert resp.status_code == 200
    assert resp.json() == {"id": u.id, "simple_mode": False}
    await db_session.refresh(u)
    assert u.simple_mode is False


@pytest.mark.asyncio
async def test_enable_for_non_executor_rejected_422(client, db_session):
    u = await _user(db_session, 3003, roles='["applicant"]')

    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": True})

    assert resp.status_code == 422
    await db_session.refresh(u)
    assert u.simple_mode is False


@pytest.mark.asyncio
async def test_disable_for_non_executor_allowed(client, db_session):
    u = await _user(db_session, 3004, roles='["applicant"]', simple_mode=True)

    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": False})

    assert resp.status_code == 200
    await db_session.refresh(u)
    assert u.simple_mode is False


@pytest.mark.asyncio
async def test_unknown_user_404(client):
    resp = await client.patch(f"{EP}/999999/simple-mode", json={"enabled": True})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extra_fields_rejected(client, db_session):
    u = await _user(db_session, 3005)
    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": True, "x": 1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_executor_cannot_toggle_own_flag_403(client, db_session):
    u = await _user(db_session, 3006)

    async def _as_executor():
        return u

    app.dependency_overrides[get_current_user] = _as_executor
    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": True})

    assert resp.status_code == 403
    await db_session.refresh(u)
    assert u.simple_mode is False


@pytest.mark.asyncio
async def test_flag_exposed_in_employee_card_and_list(client, db_session):
    on = await _user(db_session, 3007, simple_mode=True)
    off = await _user(db_session, 3008)

    card = await client.get(f"{EP}/{on.id}")
    assert card.status_code == 200
    assert card.json()["simple_mode"] is True

    listing = await client.get(EP)
    assert listing.status_code == 200
    by_id = {row["id"]: row for row in listing.json()}
    assert by_id[on.id]["simple_mode"] is True
    assert by_id[off.id]["simple_mode"] is False
