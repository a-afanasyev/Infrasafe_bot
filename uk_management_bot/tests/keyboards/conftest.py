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
    sys.modules["uk_management_bot.database.session"] = session_stub
