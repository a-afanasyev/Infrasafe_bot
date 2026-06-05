"""Tests for idempotent urgency rus→key backfill (TASK 17, alembic 015)."""
import pytest
import sqlalchemy as sa

from uk_management_bot.database.urgency_backfill import backfill_urgency_to_keys


def _conn_with_rows(urgencies):
    eng = sa.create_engine("sqlite://")
    conn = eng.connect()
    conn.execute(sa.text("CREATE TABLE requests (request_number TEXT, urgency TEXT)"))
    for i, u in enumerate(urgencies):
        conn.execute(
            sa.text("INSERT INTO requests (request_number, urgency) VALUES (:n, :u)"),
            {"n": f"r{i}", "u": u},
        )
    return conn


def _urgencies(conn):
    return sorted(r[0] for r in conn.execute(sa.text("SELECT urgency FROM requests")).fetchall())


def test_russian_converted_and_keys_unchanged():
    conn = _conn_with_rows(["Обычная", "Средняя", "Срочная", "Критическая", "low", "critical"])
    backfill_urgency_to_keys(conn)
    assert _urgencies(conn) == sorted(["low", "medium", "high", "critical", "low", "critical"])


def test_idempotent_on_rerun():
    conn = _conn_with_rows(["Срочная"])
    backfill_urgency_to_keys(conn)
    backfill_urgency_to_keys(conn)  # повторный запуск — no-op
    assert _urgencies(conn) == ["high"]


def test_unknown_value_caught_by_preflight_no_mutation():
    conn = _conn_with_rows(["Обычная", "ВообщеНеТо"])
    with pytest.raises(RuntimeError, match="preflight"):
        backfill_urgency_to_keys(conn)
    # preflight аборт до UPDATE — «Обычная» НЕ сконвертирована
    assert "Обычная" in _urgencies(conn)


def test_null_caught_by_preflight():
    conn = sa.create_engine("sqlite://").connect()
    conn.execute(sa.text("CREATE TABLE requests (request_number TEXT, urgency TEXT)"))
    conn.execute(sa.text("INSERT INTO requests (request_number, urgency) VALUES ('r0', NULL)"))
    with pytest.raises(RuntimeError):
        backfill_urgency_to_keys(conn)


def test_empty_table_noop():
    conn = _conn_with_rows([])
    backfill_urgency_to_keys(conn)  # не падает
    assert _urgencies(conn) == []
