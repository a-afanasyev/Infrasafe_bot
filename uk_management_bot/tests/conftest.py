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
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


def _async_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — postgres-only test, skipping")
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    pytest.skip(f"DATABASE_URL is not PostgreSQL ({url!r}) — postgres-only test")


@pytest_asyncio.fixture
async def address_async_engine():
    """Function-scoped: an asyncpg engine/pool is bound to the event loop it
    was created in. pytest-asyncio (asyncio_mode=auto, default function-scoped
    loop) gives each test its own loop, so a session-scoped engine would be
    used across loops → "another operation is in progress". One engine per
    test keeps engine and connections on the same loop."""
    engine = create_async_engine(_async_database_url())
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def address_async_db(address_async_engine) -> AsyncSession:
    """An AsyncSession wrapped in a rolled-back outer transaction.

    `core` functions call db.commit() freely. `join_transaction_mode=
    "create_savepoint"` (SQLAlchemy 2.0) makes the session, when bound to a
    Connection that already has a transaction, run inside a SAVEPOINT and
    automatically restart it after each commit. The outer transaction is rolled
    back at teardown, so nothing persists in the real database.

    The old manual `after_transaction_end` event-listener recipe is sync-only
    and breaks on asyncpg ("another operation is in progress"); the native
    join_transaction_mode replaces it.
    """
    conn = await address_async_engine.connect()
    outer = await conn.begin()
    session = AsyncSession(
        bind=conn,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        await session.close()
        await outer.rollback()
        await conn.close()
