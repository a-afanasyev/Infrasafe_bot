"""Stub psycopg2 + DB session so keyboards tests stay hermetic.

Дублирует подход из tests/handlers/conftest.py.
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-pw")

# Stub psycopg2 ONLY when the real driver is genuinely unavailable — a bare
# `not in sys.modules` guard installs the stub during collection and leaks it
# process-wide, breaking postgres-backed tests (e.g. tests/test_apartment_*.py).
try:
    import psycopg2  # noqa: F401 — real driver present, keep it
except Exception:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_stub.__version__ = "0.0.0-stub"
    sys.modules["psycopg2"] = psycopg2_stub

if "uk_management_bot.database.session" not in sys.modules:
    from sqlalchemy.orm import declarative_base

    session_stub = types.ModuleType("uk_management_bot.database.session")
    session_stub.Base = declarative_base()
    session_stub.engine = MagicMock(name="engine_stub")
    session_stub.async_engine = None
    session_stub.SessionLocal = MagicMock(name="SessionLocal_stub")
    session_stub.AsyncSessionLocal = None

    def _stub_get_db():  # pragma: no cover
        yield MagicMock()

    async def _stub_get_async_db():  # pragma: no cover
        yield MagicMock()

    session_stub.get_db = _stub_get_db
    session_stub.get_async_db = _stub_get_async_db

    from contextlib import contextmanager as _contextmanager

    @_contextmanager
    def _stub_session_scope():  # mirrors real session_scope (ARCH-013)
        db = session_stub.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    session_stub.session_scope = _stub_session_scope

    # AUD3-37: зеркало run_db (database/session.py). Семантика обязана совпадать
    # с реальной, потому что в полном сьюте stub подменяет модуль ДЛЯ ВСЕГО
    # процесса (sys.modules), и тесты thread-пути гоняются против него:
    #   * seam db → sync-исполнение на переданной сессии;
    #   * без db → asyncio.to_thread + session_scope, причём session_scope
    #     берётся АТРИБУТОМ модуля на момент вызова (как у реального run_db
    #     module-global lookup) — иначе patch("...database.session.session_scope")
    #     в тестах бил бы мимо.
    async def _stub_run_db(unit, *, db=None):
        if db is not None:
            return unit(db)
        import asyncio

        def _work():
            with session_stub.session_scope() as session:
                return unit(session)

        return await asyncio.to_thread(_work)

    session_stub.run_db = _stub_run_db
    sys.modules["uk_management_bot.database.session"] = session_stub
