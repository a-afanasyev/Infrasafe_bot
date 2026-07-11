"""F-02 + APIFE-14: real refresh-token rotation race against PostgreSQL.

SQLite has no row-locking (FOR UPDATE is silently dropped), so the concurrency
behaviour can only be proven on real Postgres. Two concurrent /refresh calls for
the same token serialize on ``SELECT ... FOR UPDATE``: exactly one rotates; the
loser sees the just-rotated token and — under APIFE-14 reuse detection — treats
it as a replay and revokes the whole family fail-closed (so a double-submit the
client failed to dedup ends in re-auth, never two live sessions).

Isolation: own temp schema in the same DB. Skipped when DATABASE_URL is not
Postgres (POSTGRES_TEST_URL, bridged from DATABASE_URL in tests/api/conftest.py).
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.refresh_token import RefreshToken
from uk_management_bot.database.session import Base
from uk_management_bot.api.auth.router import (
    _rotate_refresh_token, _REFRESH_OK, _REFRESH_INVALID,
)
from uk_management_bot.api.auth.service import hash_token, create_refresh_token_value

SCHEMA = "auth_refresh_race_test"
_TABLES = [User.__table__, RefreshToken.__table__]


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_TEST_URL", "")
    if not url.startswith("postgresql"):
        return None
    return url.replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture
async def auth_pg_factory():
    url = _pg_url()
    if url is None:
        pytest.skip("POSTGRES_TEST_URL not set — refresh-race suite skipped")

    engine = create_async_engine(
        url,
        execution_options={"schema_translate_map": {None: SCHEMA}},
        pool_size=10,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            await conn.run_sync(lambda sc: Base.metadata.create_all(sc, tables=_TABLES))
    except Exception as exc:  # pragma: no cover — host without reachable PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


async def _seed_user_with_token(factory, *, family_id="fam-1") -> tuple[int, str]:
    """Approved user + one valid refresh token in the given family."""
    token_value = create_refresh_token_value()
    async with factory() as db:
        user = User(telegram_id=515151, username="rot", first_name="Rot",
                    roles='["manager"]', active_role="manager", status="approved")
        db.add(user)
        await db.flush()
        db.add(RefreshToken(
            user_id=user.id,
            token_hash=hash_token(token_value),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            family_id=family_id,
        ))
        uid = user.id
        await db.commit()
    return uid, token_value


async def _rotate(factory, token_value):
    async with factory() as db:
        return await _rotate_refresh_token(db, token_value, ttl=None)


async def _active_count(factory, uid) -> int:
    async with factory() as db:
        return (await db.execute(
            select(func.count(RefreshToken.id)).where(
                RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None)
            )
        )).scalar()


@pytest.mark.asyncio
async def test_concurrent_refresh_never_yields_two_sessions(auth_pg_factory):
    uid, token_value = await _seed_user_with_token(auth_pg_factory)

    r1, r2 = await asyncio.gather(
        _rotate(auth_pg_factory, token_value),
        _rotate(auth_pg_factory, token_value),
    )
    # Exactly one rotation wins; the other serializes behind the lock and 401s.
    assert sorted([r1[0], r2[0]]) == [_REFRESH_INVALID, _REFRESH_OK]

    # APIFE-14 fail-closed: the loser treats the just-rotated token as a replay
    # and revokes the whole family — including the winner's fresh replacement.
    # Net: zero live sessions (never two), user must re-authenticate.
    assert await _active_count(auth_pg_factory, uid) == 0

    # The winner's replacement is therefore no longer usable.
    winner = r1 if r1[0] == _REFRESH_OK else r2
    outcome, _u, _n = await _rotate(auth_pg_factory, winner[2])
    assert outcome == _REFRESH_INVALID


@pytest.mark.asyncio
async def test_sequential_rotation_chain_stays_in_family(auth_pg_factory):
    uid, token_value = await _seed_user_with_token(auth_pg_factory, family_id="famX")

    o1, _u1, v1 = await _rotate(auth_pg_factory, token_value)
    assert o1 == _REFRESH_OK
    o2, _u2, v2 = await _rotate(auth_pg_factory, v1)
    assert o2 == _REFRESH_OK
    assert v2 and v2 != v1

    # After a clean sequential chain exactly one active token remains, in famX.
    assert await _active_count(auth_pg_factory, uid) == 1
    async with auth_pg_factory() as db:
        active = (await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None)
            )
        )).scalar_one()
        assert active.family_id == "famX"


@pytest.mark.asyncio
async def test_concurrent_race_leaves_other_family_untouched(auth_pg_factory):
    uid, a_value = await _seed_user_with_token(auth_pg_factory, family_id="famA")
    # a second login (different family) for the same user
    b_value = create_refresh_token_value()
    async with auth_pg_factory() as db:
        db.add(RefreshToken(
            user_id=uid, token_hash=hash_token(b_value),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7), family_id="famB",
        ))
        await db.commit()

    # race famA to trigger fail-closed revoke of famA
    await asyncio.gather(
        _rotate(auth_pg_factory, a_value),
        _rotate(auth_pg_factory, a_value),
    )

    # famB (other device) survives and is still rotatable
    outcome, _u, _n = await _rotate(auth_pg_factory, b_value)
    assert outcome == _REFRESH_OK
