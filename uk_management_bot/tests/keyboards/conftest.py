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

if "psycopg2" not in sys.modules:
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
    sys.modules["uk_management_bot.database.session"] = session_stub
