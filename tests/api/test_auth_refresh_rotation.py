"""F-02 + APIFE-14: /refresh rotation contract and token-family reuse detection
(SQLite, non-concurrent). The concurrency guarantee (row lock) is proven against
Postgres in test_auth_refresh_pg_concurrency.py.

Family model (APIFE-14): one family per login; rotation keeps the family and
marks the old token reason=rotated. Replaying a *rotated* token = fail-closed
revoke of the whole family. Replaying a *logout*/admin/legacy token = plain 401,
no family-wide revoke (so a stale logout token can't DoS the account).
"""
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.refresh_token import (
    RefreshToken, REASON_ROTATED, REASON_LOGOUT, REASON_REUSE,
)
from uk_management_bot.api.auth.service import hash_token, create_refresh_token_value
from uk_management_bot.api.auth.router import (
    _rotate_refresh_token, _REFRESH_OK, _REFRESH_INVALID,
)

REFRESH_URL = "/api/v2/auth/refresh"


@pytest_asyncio.fixture
async def token_user(db_session):
    u = User(telegram_id=616161, username="reftest", first_name="Ref", last_name="Test",
             roles='["manager"]', active_role="manager", status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _seed_token(db, user_id, *, family_id="fam-1", reason=None, revoked=False) -> str:
    value = create_refresh_token_value()
    now = datetime.now(timezone.utc)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=hash_token(value),
        expires_at=now + timedelta(days=7),
        family_id=family_id,
        revoked_at=now if revoked else None,
        revocation_reason=reason,
    ))
    await db.commit()
    return value


async def _active_count(db, user_id) -> int:
    return (await db.execute(
        select(func.count(RefreshToken.id)).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )).scalar()


# ── HTTP contract ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_rotates_and_returns_new_token(client, db_session, token_user):
    value = await _seed_token(db_session, token_user.id)
    r = await client.post(REFRESH_URL, json={"refresh_token": value})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"] and body["refresh_token"] != value


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_401(client):
    r = await client.post(REFRESH_URL, json={"refresh_token": "does-not-exist"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_reused_rotated_token_is_rejected(client, db_session, token_user):
    value = await _seed_token(db_session, token_user.id)
    first = await client.post(REFRESH_URL, json={"refresh_token": value})
    assert first.status_code == 200, first.text
    second = await client.post(REFRESH_URL, json={"refresh_token": value})
    assert second.status_code == 401


# ── APIFE-14 family semantics (direct _rotate_refresh_token) ──────────

@pytest.mark.asyncio
async def test_normal_rotation_preserves_family_and_marks_reason(db_session, token_user):
    value = await _seed_token(db_session, token_user.id, family_id="famA")

    outcome, user, new_value = await _rotate_refresh_token(db_session, value, ttl=None)
    assert outcome == _REFRESH_OK
    assert user.id == token_user.id

    old = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(value))
    )).scalar_one()
    child = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(new_value))
    )).scalar_one()
    assert old.revoked_at is not None and old.revocation_reason == REASON_ROTATED
    assert child.family_id == "famA"          # child stays in the same family
    assert child.parent_token_id == old.id     # lineage recorded
    assert child.revoked_at is None


@pytest.mark.asyncio
async def test_replaying_rotated_token_revokes_whole_family(db_session, token_user):
    value = await _seed_token(db_session, token_user.id, family_id="famA")
    # rotate once so `value` becomes a rotated token; child is active
    _o, _u, child_value = await _rotate_refresh_token(db_session, value, ttl=None)
    assert await _active_count(db_session, token_user.id) == 1

    # replay the rotated original → fail-closed: the whole family is revoked
    outcome, _u2, _n = await _rotate_refresh_token(db_session, value, ttl=None)
    assert outcome == _REFRESH_INVALID
    assert await _active_count(db_session, token_user.id) == 0  # child revoked too

    child = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(child_value))
    )).scalar_one()
    assert child.revocation_reason == REASON_REUSE


@pytest.mark.asyncio
async def test_reuse_revokes_only_its_own_family(db_session, token_user):
    # two independent logins → two families for the same user
    a_value = await _seed_token(db_session, token_user.id, family_id="famA")
    b_value = await _seed_token(db_session, token_user.id, family_id="famB")
    # rotate A once so its original becomes a rotated token
    await _rotate_refresh_token(db_session, a_value, ttl=None)

    # replay A's rotated original → revoke famA only
    outcome, _u, _n = await _rotate_refresh_token(db_session, a_value, ttl=None)
    assert outcome == _REFRESH_INVALID

    # famB (the other device/login) is untouched and still rotatable
    outcome_b, user_b, _nb = await _rotate_refresh_token(db_session, b_value, ttl=None)
    assert outcome_b == _REFRESH_OK
    assert user_b.id == token_user.id


@pytest.mark.asyncio
async def test_logout_token_replay_does_not_revoke_family(db_session, token_user):
    # a logged-out token in famA; a sibling active token in the same family
    logged_out = await _seed_token(db_session, token_user.id, family_id="famA",
                                   reason=REASON_LOGOUT, revoked=True)
    sibling = await _seed_token(db_session, token_user.id, family_id="famA")

    # replaying the logout token must NOT nuke the family (no rotation replay)
    outcome, _u, _n = await _rotate_refresh_token(db_session, logged_out, ttl=None)
    assert outcome == _REFRESH_INVALID

    sib = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(sibling))
    )).scalar_one()
    assert sib.revoked_at is None  # family survived a stale-logout replay
