"""DB-051 / DB-053 / DB-054 — structural sentinel for migration 012.

Postgres-only (the partial-index ``WHERE`` clauses and the ``pg_constraint``
shape are pg-specific). Skips when ``DATABASE_URL`` isn't a postgres DSN, like
the DB-111 sentinel (``test_apartment_fk_shape.py``). Guards that a future
migration can't silently drop these hot-path indexes or regress the
board_config FK shape.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url or not url.startswith("postgres"):
        pytest.skip("DATABASE_URL not postgres — pg-only test, skipping")
    return url


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_database_url(), future=True)
    yield eng
    eng.dispose()


def _indexes(engine, table: str) -> dict[str, str]:
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :t"),
            {"t": table},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def test_notifications_fk_and_partial_indexes_exist(engine):
    idx = _indexes(engine, "notifications")
    assert "ix_notifications_user_id" in idx
    assert "ix_notifications_request_number_fk" in idx
    assert "ix_notifications_user_unread" in idx
    # partial predicate present
    assert "is_read" in idx["ix_notifications_user_unread"].lower()


def test_webhook_outbox_pending_partial_index_exists(engine):
    idx = _indexes(engine, "webhook_outbox")
    assert "ix_webhook_outbox_pending" in idx
    defn = idx["ix_webhook_outbox_pending"].lower()
    assert "pending" in defn and "where" in defn


def test_board_config_updated_by_index_and_fk(engine):
    idx = _indexes(engine, "board_config")
    assert "ix_board_config_updated_by" in idx

    with engine.connect() as c:
        row = c.execute(text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conrelid = 'board_config'::regclass AND contype = 'f' "
            "AND conname = 'board_config_updated_by_fkey'"
        )).fetchone()
    assert row is not None, "board_config_updated_by_fkey FK missing"
    assert row[0] == "n", "FK must be ON DELETE SET NULL (confdeltype='n')"
