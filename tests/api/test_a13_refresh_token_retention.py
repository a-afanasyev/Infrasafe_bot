"""Аудит #13 (A13-06): отжившие refresh-токены удаляются по расписанию.

На profk 8752 из 9025 строк `refresh_tokens` были просрочены или отозваны:
таблицу никто не чистил. Живые сессии и свежеотозванные токены (по ним
работает обнаружение повтора) задание не трогает.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from uk_management_bot.database.models.refresh_token import RefreshToken
from uk_management_bot.database.models.user import User
from uk_management_bot.services.outbox_retention import purge_dead_refresh_tokens

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def owner_id(db_session_factory) -> int:
    async with db_session_factory() as db:
        user = User(telegram_id=881100, first_name="T", roles='["applicant"]', status="approved")
        db.add(user)
        await db.commit()
        return user.id


def _token(owner: int, name: str, *, expires_in_days: int, revoked_days_ago: int | None = None) -> RefreshToken:
    return RefreshToken(
        user_id=owner, token_hash=name.ljust(64, "0"), family_id=name,
        expires_at=NOW + timedelta(days=expires_in_days),
        revoked_at=None if revoked_days_ago is None else NOW - timedelta(days=revoked_days_ago),
    )


@pytest.mark.asyncio
async def test_purges_only_long_dead_tokens(monkeypatch, db_session_factory, owner_id):
    monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal", db_session_factory)
    async with db_session_factory() as db:
        db.add_all([
            _token(owner_id, "live", expires_in_days=5),
            _token(owner_id, "expired-recently", expires_in_days=-3),
            _token(owner_id, "revoked-recently", expires_in_days=5, revoked_days_ago=2),
            _token(owner_id, "expired-long-ago", expires_in_days=-40),
            _token(owner_id, "revoked-long-ago", expires_in_days=5, revoked_days_ago=40),
        ])
        await db.commit()

    assert await purge_dead_refresh_tokens(retention_days=30) == {"deleted": 2}

    async with db_session_factory() as db:
        left = sorted((await db.execute(select(RefreshToken.family_id))).scalars())
    assert left == ["expired-recently", "live", "revoked-recently"]


@pytest.mark.asyncio
async def test_db_unavailable_does_not_raise(monkeypatch):
    monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal", None)
    assert await purge_dead_refresh_tokens() == {"deleted": 0, "error": "db_unavailable"}
