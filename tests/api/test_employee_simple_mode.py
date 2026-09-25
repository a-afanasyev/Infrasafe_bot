"""Простой режим исполнителя: менеджер включает/выключает флаг сотруднику.

`PATCH /api/v2/shifts/employees/{id}/simple-mode {enabled}` и
`PATCH .../{id}/language {language}` — только manager и только над
сотрудником: житель (не staff) → 422 как в activate/decline, manager/admin
(в т.ч. мульти-роль) → 403 как в approve/block/rename (`_ensure_not_privileged`).
Включить simple_mode можно только исполнителю, выключить — любому сотруднику
(флаг не застревает, если роль исполнителя уже сняли). Флаг виден в карточке и
списке сотрудников.
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
async def test_enable_for_non_executor_staff_rejected_422(client, db_session):
    u = await _user(db_session, 3003, roles='["inspector"]')

    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": True})

    assert resp.status_code == 422
    await db_session.refresh(u)
    assert u.simple_mode is False


@pytest.mark.asyncio
async def test_disable_for_non_executor_staff_allowed(client, db_session):
    u = await _user(db_session, 3004, roles='["inspector"]', simple_mode=True)

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


# ═══════════════════ Язык сотрудника (меняет менеджер) ═══════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "uz", "uz_cyrl"])
async def test_manager_sets_employee_language(client, db_session, language):
    u = await _user(db_session, 3100 + len(language))

    resp = await client.patch(f"{EP}/{u.id}/language", json={"language": language})

    assert resp.status_code == 200
    assert resp.json() == {"id": u.id, "language": language}
    await db_session.refresh(u)
    assert u.language == language


@pytest.mark.asyncio
async def test_unsupported_language_rejected_422(client, db_session):
    u = await _user(db_session, 3110)
    resp = await client.patch(f"{EP}/{u.id}/language", json={"language": "en"})
    assert resp.status_code == 422
    await db_session.refresh(u)
    assert u.language == "ru"


@pytest.mark.asyncio
async def test_language_extra_fields_rejected(client, db_session):
    u = await _user(db_session, 3111)
    resp = await client.patch(f"{EP}/{u.id}/language", json={"language": "uz", "x": 1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_language_unknown_user_404(client):
    resp = await client.patch(f"{EP}/999999/language", json={"language": "uz"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_executor_cannot_set_language_via_manager_endpoint_403(client, db_session):
    u = await _user(db_session, 3112)

    async def _as_executor():
        return u

    app.dependency_overrides[get_current_user] = _as_executor
    resp = await client.patch(f"{EP}/{u.id}/language", json={"language": "uz"})
    assert resp.status_code == 403


def test_language_validation_shares_profile_source():
    """Один источник допустимых языков — профиль и карточка сотрудника не расходятся."""
    from uk_management_bot.api.profile.router import ALLOWED_LANGUAGES
    from uk_management_bot.api.shifts import schemas

    assert schemas.ALLOWED_LANGUAGES is ALLOWED_LANGUAGES


@pytest.mark.asyncio
async def test_language_exposed_in_employee_card_and_list(client, db_session):
    u = await _user(db_session, 3113)
    u.language = "uz_cyrl"
    await db_session.commit()

    card = await client.get(f"{EP}/{u.id}")
    assert card.json()["language"] == "uz_cyrl"
    listing = await client.get(EP)
    assert {row["id"]: row for row in listing.json()}[u.id]["language"] == "uz_cyrl"


# ═══════════════════ Guard цели: только сотрудник, не manager/admin ═══════════════════

_PRIVILEGED = ['["manager"]', '["admin"]', '["manager", "executor"]', '["applicant", "admin", "executor"]']
_CALLS = [
    ("simple-mode", {"enabled": True}),
    ("simple-mode", {"enabled": False}),
    ("language", {"language": "uz"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", _PRIVILEGED)
@pytest.mark.parametrize("path,body", _CALLS)
async def test_privileged_target_forbidden_403(client, db_session, roles, path, body):
    u = await _user(db_session, 3200 + _PRIVILEGED.index(roles), roles=roles, simple_mode=True)

    resp = await client.patch(f"{EP}/{u.id}/{path}", json=body)

    assert resp.status_code == 403
    await db_session.refresh(u)
    assert u.simple_mode is True
    assert u.language == "ru"


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body", _CALLS)
async def test_resident_target_rejected_422(client, db_session, path, body):
    u = await _user(db_session, 3210, roles='["applicant"]', simple_mode=True)

    resp = await client.patch(f"{EP}/{u.id}/{path}", json=body)

    assert resp.status_code == 422
    await db_session.refresh(u)
    assert u.simple_mode is True
    assert u.language == "ru"


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ['["executor"]', '["applicant", "executor"]', '["inspector"]'])
async def test_staff_target_language_ok(client, db_session, roles):
    u = await _user(db_session, 3220 + len(roles), roles=roles)

    resp = await client.patch(f"{EP}/{u.id}/language", json={"language": "uz_cyrl"})

    assert resp.status_code == 200
    await db_session.refresh(u)
    assert u.language == "uz_cyrl"


@pytest.mark.asyncio
async def test_applicant_executor_enable_ok(client, db_session):
    u = await _user(db_session, 3230, roles='["applicant", "executor"]')
    resp = await client.patch(f"{EP}/{u.id}/simple-mode", json={"enabled": True})
    assert resp.status_code == 200
