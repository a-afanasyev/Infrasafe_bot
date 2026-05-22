"""Shared fixtures for uk_management_bot/tests/.

Only DEFINES fixtures (no import-time side effects), so existing tests in this
directory are unaffected — fixtures are opt-in by name.

The address-core fixtures (ARCH-014) run against the real PostgreSQL the bot
uses (same DATABASE_URL). Tests are skipped when DATABASE_URL is unset, mirroring
test_apartment_purge.py. Isolation uses the SQLAlchemy "join an external
transaction" pattern: the session runs inside a SAVEPOINT, so `core`'s internal
db.commit() commits only the savepoint; the outer transaction is rolled back at
teardown and nothing persists in the real database.
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker,
)


def _async_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — postgres-only test, skipping")
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    pytest.skip(f"DATABASE_URL is not PostgreSQL ({url!r}) — postgres-only test")


@pytest_asyncio.fixture(scope="session")
async def address_async_engine():
    engine = create_async_engine(_async_database_url())
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def address_async_db(address_async_engine) -> AsyncSession:
    """An AsyncSession wrapped in a rolled-back outer transaction.

    `core` functions can call db.commit() freely — it commits a SAVEPOINT that
    is discarded when the fixture tears the outer transaction down.
    """
    conn = await address_async_engine.connect()
    outer = await conn.begin()
    maker = async_sessionmaker(bind=conn, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    await session.begin_nested()

    @event.listens_for(session.sync_session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        await outer.rollback()
        await conn.close()
