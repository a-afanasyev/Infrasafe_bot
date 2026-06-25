"""AUD3-16 (A07) — POST /api/v2/auth/set-password must require the CURRENT
password when one already exists (change flow), while still allowing the
first-time set flow (no password yet) without it.

A valid access token alone must NOT be enough to overwrite an existing
password — otherwise a replayed/stolen token silently takes over the account.

Rate-limit note: set-password is capped 5/min per client IP (SEC-019). Each
request below carries a unique TEST-NET-3 X-Real-IP so buckets never collide
across tests / reruns (same trick as test_auth_set_password_rate_limit.py).
"""
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.api.auth.service import hash_password, verify_password
from uk_management_bot.database.models.user import User

CURRENT = "OldPassword123"
NEW = "NewPassword456"


def _ip(salt: int = 0) -> str:
    base = (time.monotonic_ns() >> 4) & 0xFF
    octet = (base + salt) % 256
    if octet in (0, 255):
        octet = 1
    return f"203.0.113.{octet}"


def _h(salt: int = 0) -> dict:
    return {"X-Real-IP": _ip(salt)}


@pytest_asyncio.fixture
async def user_with_password(db_session):
    user = User(
        telegram_id=777111,
        username="haspw",
        first_name="Has",
        roles='["manager"]',
        active_role="manager",
        status="approved",
        password_hash=hash_password(CURRENT),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client_pw(db_session_factory, user_with_password):
    """Client authenticated as a user who ALREADY has a password."""

    async def override_get_db():
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_get_current_user():
        return user_with_password

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _fetch_hash(db_session_factory, user_id: int) -> str | None:
    async with db_session_factory() as s:
        row = await s.execute(select(User).where(User.id == user_id))
        return row.scalar_one().password_hash


@pytest.mark.asyncio
async def test_change_with_correct_current_succeeds(client_pw, db_session_factory, user_with_password):
    r = await client_pw.post(
        "/api/v2/auth/set-password",
        json={"password": NEW, "confirm_password": NEW, "current_password": CURRENT},
        headers=_h(1),
    )
    assert r.status_code == 200, r.text
    new_hash = await _fetch_hash(db_session_factory, user_with_password.id)
    assert verify_password(NEW, new_hash)
    assert not verify_password(CURRENT, new_hash)


@pytest.mark.asyncio
async def test_change_without_current_rejected(client_pw, db_session_factory, user_with_password):
    r = await client_pw.post(
        "/api/v2/auth/set-password",
        json={"password": NEW, "confirm_password": NEW},
        headers=_h(2),
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "current_password_required"
    # Password unchanged — still the original.
    unchanged = await _fetch_hash(db_session_factory, user_with_password.id)
    assert verify_password(CURRENT, unchanged)


@pytest.mark.asyncio
async def test_change_with_wrong_current_rejected(client_pw, db_session_factory, user_with_password):
    r = await client_pw.post(
        "/api/v2/auth/set-password",
        json={"password": NEW, "confirm_password": NEW, "current_password": "WrongOne999"},
        headers=_h(3),
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "current_password_invalid"
    unchanged = await _fetch_hash(db_session_factory, user_with_password.id)
    assert verify_password(CURRENT, unchanged)


@pytest.mark.asyncio
async def test_first_time_set_needs_no_current(client, db_session_factory):
    """manager_user (default client fixture) has no password_hash — first-time
    set must succeed without current_password."""
    r = await client.post(
        "/api/v2/auth/set-password",
        json={"password": NEW, "confirm_password": NEW},
        headers=_h(4),
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_profile_reports_has_password_true(client_pw):
    r = await client_pw.get("/api/v2/profile")
    assert r.status_code == 200, r.text
    assert r.json()["has_password"] is True


@pytest.mark.asyncio
async def test_profile_reports_has_password_false(client):
    r = await client.get("/api/v2/profile")
    assert r.status_code == 200, r.text
    assert r.json()["has_password"] is False
