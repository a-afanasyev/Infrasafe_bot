"""A10 — аудит безопасности 2026-10-23 (`docs/audit/2026-10-23-security-audit.md`): пин-тесты API.

API-01 менеджерский инвайт/активация — аудит + суперадмины; API-02 meter-entry
только над рядовым сотрудником; API-03 дубль email → 409; API-05 потолок тела
вебхука; API-06 лимиты колл-центра; API-07 access-токен без `exp` не принимается;
API-08 legacy cookie `access_token` не аутентифицирует; INF-05 аудит входа.
"""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from starlette.requests import Request

from uk_management_bot.api.auth import audit as login_audit
from uk_management_bot.api.auth.service import create_access_token, encode_jwt, verify_access_token
from uk_management_bot.api.callcenter.schemas import CallCenterCreateRequest
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.shifts.router import employees as employees_mod
from uk_management_bot.api.shifts.service import manager_grant as _manager_grant
from uk_management_bot.api.shifts.schemas import CreateInviteRequest
from uk_management_bot.api.webhooks.router import MAX_WEBHOOK_BODY_BYTES
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User

EP = "/api/v2/shifts/employees"


async def _user(db, tg, *, roles, status="approved", **extra):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="U", last_name=str(tg),
             roles=roles, active_role=roles.strip('[]"'), status=status,
             verification_status="verified", **extra)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _audit_rows(db, action):
    return (await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars().all()


@pytest.fixture
def captured_notifications(monkeypatch):
    sent: list[str] = []

    async def _notify(text):
        sent.append(text)
        return 1

    monkeypatch.setattr(_manager_grant, "notify_superadmins", _notify)
    return sent


# ── API-01 ───────────────────────────────────────────────────────────

def _patch_invite_generation(monkeypatch):
    import uk_management_bot.database.session as session_mod
    import uk_management_bot.services.invite_service as invite_mod

    async def _username():
        return "profkbot"

    class _FakeSession:
        def close(self):
            pass

    class _FakeInviteService:
        def __init__(self, db):
            pass

        def generate_invite(self, role, created_by, specialization=None, hours=24):
            return "invite_v1:ok.sig"

    monkeypatch.setattr(employees_mod, "_resolve_bot_username", _username)
    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(invite_mod, "InviteService", _FakeInviteService)


@pytest.mark.asyncio
async def test_manager_invite_is_audited_and_reported(monkeypatch, db_session, manager_user, captured_notifications):
    _patch_invite_generation(monkeypatch)
    body = CreateInviteRequest(role="manager", specializations=[], hours=24)

    await employees_mod.create_invite(body=body, db=db_session, current_user=manager_user)

    rows = await _audit_rows(db_session, _manager_grant.ACTION_INVITE)
    assert len(rows) == 1
    assert rows[0].user_id == manager_user.id
    assert rows[0].details["hours"] == 24
    assert captured_notifications and "manager" in captured_notifications[0]


@pytest.mark.asyncio
async def test_executor_invite_is_not_reported(monkeypatch, db_session, manager_user, captured_notifications):
    _patch_invite_generation(monkeypatch)
    body = CreateInviteRequest(role="executor", specializations=["plumber"], hours=24)

    await employees_mod.create_invite(body=body, db=db_session, current_user=manager_user)

    assert await _audit_rows(db_session, _manager_grant.ACTION_INVITE) == []
    assert captured_notifications == []


@pytest.mark.asyncio
async def test_manager_activation_is_audited_and_reported(client, db_session, manager_user, captured_notifications):
    pending = await _user(db_session, 4101, roles='["manager"]', status="pending")

    resp = await client.patch(f"{EP}/{pending.id}/activate")

    assert resp.status_code == 200, resp.text
    rows = await _audit_rows(db_session, _manager_grant.ACTION_ACTIVATED)
    assert len(rows) == 1
    assert rows[0].user_id == manager_user.id
    assert rows[0].details["target_user_id"] == pending.id
    assert captured_notifications and str(pending.telegram_id) in captured_notifications[0]


@pytest.mark.asyncio
async def test_executor_activation_is_silent(client, db_session, captured_notifications):
    pending = await _user(db_session, 4102, roles='["executor"]', status="pending")

    resp = await client.patch(f"{EP}/{pending.id}/activate")

    assert resp.status_code == 200, resp.text
    assert await _audit_rows(db_session, _manager_grant.ACTION_ACTIVATED) == []
    assert captured_notifications == []


# ── API-02 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_meter_entry_cannot_target_manager(client, db_session):
    other_manager = await _user(db_session, 4201, roles='["manager"]')

    resp = await client.patch(f"{EP}/{other_manager.id}/meter-entry", json={"enabled": True})

    assert resp.status_code == 403
    await db_session.refresh(other_manager)
    assert "resource_meter_entry" not in (other_manager.roles or "")


@pytest.mark.asyncio
async def test_meter_entry_cannot_target_resident(client, resident_user):
    resp = await client.patch(f"{EP}/{resident_user.id}/meter-entry", json={"enabled": True})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_meter_entry_still_works_for_executor(client, db_session):
    executor = await _user(db_session, 4203, roles='["executor"]')

    resp = await client.patch(f"{EP}/{executor.id}/meter-entry", json={"enabled": True})

    assert resp.status_code == 200
    assert resp.json() == {"id": executor.id, "meter_entry": True}


# ── API-03 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_duplicate_email_is_409_not_500(client, db_session, resident_user):
    resident_user.email = "taken@example.com"
    await db_session.commit()

    resp = await client.patch("/api/v2/profile", json={"email": "taken@example.com"})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Email is already in use"


@pytest.mark.asyncio
async def test_profile_free_email_is_accepted(client, db_session, manager_user):
    resp = await client.patch("/api/v2/profile", json={"email": "free@example.com"})

    assert resp.status_code == 200
    await db_session.refresh(manager_user)
    assert manager_user.email == "free@example.com"


# ── API-05 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_oversized_body_rejected_before_signature(client):
    resp = await client.post(
        "/api/v2/webhooks/infrasafe/alert",
        content=b"x" * (MAX_WEBHOOK_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 413


# ── API-06 ───────────────────────────────────────────────────────────

def test_callcenter_description_is_capped_like_resident_request():
    with pytest.raises(ValidationError):
        CallCenterCreateRequest(category="Электрика", urgency="Обычная", description="x" * 2001)
    CallCenterCreateRequest(category="Электрика", urgency="Обычная", description="x" * 2000)


def test_callcenter_caller_fields_are_capped():
    with pytest.raises(ValidationError):
        CallCenterCreateRequest(
            category="Электрика", urgency="Обычная", description="ok", caller_phone="9" * 33
        )


# ── API-07 ───────────────────────────────────────────────────────────

def test_access_token_without_exp_is_rejected():
    eternal = encode_jwt({"sub": "1", "roles": ["manager"]})
    assert verify_access_token(eternal) is None


def test_access_token_without_sub_is_rejected():
    from datetime import datetime, timedelta, timezone

    no_sub = encode_jwt({"roles": ["manager"], "exp": datetime.now(timezone.utc) + timedelta(minutes=5)})
    assert verify_access_token(no_sub) is None


def test_regular_access_token_still_valid():
    assert verify_access_token(create_access_token(1, ["manager"]))["sub"] == "1"


# ── API-08 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_legacy_access_token_cookie_no_longer_authenticates(db_session, manager_user):
    token = create_access_token(manager_user.id, ["manager"])
    scope = {
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(b"cookie", f"access_token={token}".encode())],
    }

    with pytest.raises(HTTPException) as exc:
        await get_current_user(Request(scope), credentials=None, db=db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_uk_access_cookie_authenticates(db_session, manager_user):
    token = create_access_token(manager_user.id, ["manager"])
    scope = {
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(b"cookie", f"uk_access={token}".encode())],
    }

    user = await get_current_user(Request(scope), credentials=None, db=db_session)
    assert user.id == manager_user.id


# ── INF-05 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failed_password_login_is_audited_without_email(client, db_session):
    resp = await client.post(
        "/api/v2/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )

    assert resp.status_code == 401
    rows = await _audit_rows(db_session, login_audit.LOGIN_FAILED)
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].details["method"] == "password"
    assert "nobody" not in str(rows[0].details)
    assert rows[0].details["login_hash"] == login_audit._login_hash("nobody@example.com")
