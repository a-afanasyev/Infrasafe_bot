"""Tests for idempotent returned-status backfill (SSOT cutover PR3, alembic 019)."""
import sqlalchemy as sa

from uk_management_bot.database.returned_status_backfill import (
    backfill_returned_status,
    revert_returned_status,
)


def _conn_with_rows(rows):
    """rows: list of (status, manager_confirmed, is_returned)."""
    eng = sa.create_engine("sqlite://")
    conn = eng.connect()
    conn.execute(sa.text(
        "CREATE TABLE requests (request_number TEXT, status TEXT, "
        "manager_confirmed BOOLEAN, is_returned BOOLEAN)"
    ))
    for i, (st, mc, ir) in enumerate(rows):
        conn.execute(
            sa.text(
                "INSERT INTO requests (request_number, status, manager_confirmed, "
                "is_returned) VALUES (:n, :s, :mc, :ir)"
            ),
            {"n": f"r{i}", "s": st, "mc": 1 if mc else 0, "ir": 1 if ir else 0},
        )
    return conn


def _statuses(conn):
    return sorted(r[0] for r in conn.execute(
        sa.text("SELECT status FROM requests")).fetchall())


def test_returned_legacy_converted_to_canon():
    # Исполнено+is_returned → Возвращена; is_returned остаётся.
    conn = _conn_with_rows([("Исполнено", False, True)])
    res = backfill_returned_status(conn)
    assert res["to_returned"] == 1
    assert _statuses(conn) == ["Возвращена"]
    ir = conn.execute(sa.text("SELECT is_returned FROM requests")).scalar()
    assert ir in (1, True)  # исторический флаг сохранён


def test_telegram_composite_confirmed_converted_to_completed():
    # Выполнена+manager_confirmed ¬returned → Исполнено.
    conn = _conn_with_rows([("Выполнена", True, False)])
    res = backfill_returned_status(conn)
    assert res["to_completed"] == 1
    assert _statuses(conn) == ["Исполнено"]


def test_canon_and_unrelated_rows_untouched():
    conn = _conn_with_rows([
        ("Исполнено", True, False),    # genuine completed — без is_returned, не трогаем
        ("Возвращена", False, True),   # уже канон — не трогаем
        ("Выполнена", False, False),   # ещё не подтверждена — не трогаем
        ("Новая", False, False),
    ])
    res = backfill_returned_status(conn)
    assert res == {"to_returned": 0, "to_completed": 0}
    assert _statuses(conn) == ["Возвращена", "Выполнена", "Исполнено", "Новая"]


def test_idempotent_on_rerun():
    conn = _conn_with_rows([("Исполнено", False, True), ("Выполнена", True, False)])
    backfill_returned_status(conn)
    res2 = backfill_returned_status(conn)  # повторный запуск — no-op
    assert res2 == {"to_returned": 0, "to_completed": 0}
    assert _statuses(conn) == ["Возвращена", "Исполнено"]


def test_revert_returns_canon_to_completed():
    conn = _conn_with_rows([("Исполнено", False, True)])
    backfill_returned_status(conn)
    assert _statuses(conn) == ["Возвращена"]
    n = revert_returned_status(conn)
    assert n == 1
    assert _statuses(conn) == ["Исполнено"]


def test_empty_table_noop():
    conn = _conn_with_rows([])
    res = backfill_returned_status(conn)
    assert res == {"to_returned": 0, "to_completed": 0}
