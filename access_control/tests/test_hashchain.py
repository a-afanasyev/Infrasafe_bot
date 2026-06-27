"""Целостность hash-chain append-only таблиц (§9.7, решение CTO #9) — postgres-only.

Проверяет СВЯЗНОСТЬ цепочки: для двух последовательных записей append-only
``prev_hash`` второй равен ``row_hash`` первой (per-table chain). Невозможность
подмены гарантируется отдельным BEFORE UPDATE/DELETE триггером (см.
``test_append_only.py``) — здесь это не дублируется.

Цепочка пишется сервисным слоем ingestion: каждый приём создаёт строку в
``access_decisions`` и ``access_events`` с вычисленными ``prev_hash``/``row_hash``.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from access_control.services.hashchain import _table_lock_key, next_hash
from access_control.services.ingestion import ingest_anpr
from access_control.tests.conftest import seed_permanent_vehicle, utcnow
from access_control.tests.test_ingestion import _payload


def _chain(db, table: str):
    return db.execute(
        text(f"SELECT id, prev_hash, row_hash FROM {table} ORDER BY id ASC")
    ).all()


def test_decision_chain_links_prev_to_prior_row_hash(pg_db, pilot) -> None:
    """access_decisions: первая запись — genesis (prev_hash IS NULL), у второй
    prev_hash == row_hash первой."""
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    t1 = utcnow()
    t2 = t1 + dt.timedelta(minutes=5)  # вне окна дедупа — два разных приезда

    ingest_anpr(pg_db, _payload(pilot, event_id="hc-d1", plate="01A001AA", captured_at=t1))
    ingest_anpr(pg_db, _payload(pilot, event_id="hc-d2", plate="01A001AA", captured_at=t2))

    rows = _chain(pg_db, "access_decisions")
    assert len(rows) == 2
    first, second = rows
    assert first.prev_hash is None
    assert first.row_hash is not None
    assert second.prev_hash == first.row_hash
    assert second.row_hash != first.row_hash


def test_event_chain_links_prev_to_prior_row_hash(pg_db, pilot) -> None:
    """access_events: та же связность цепочки, что и у решений."""
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    t1 = utcnow()
    t2 = t1 + dt.timedelta(minutes=5)

    ingest_anpr(pg_db, _payload(pilot, event_id="hc-e1", plate="01A001AA", captured_at=t1))
    ingest_anpr(pg_db, _payload(pilot, event_id="hc-e2", plate="01A001AA", captured_at=t2))

    rows = _chain(pg_db, "access_events")
    assert len(rows) == 2
    first, second = rows
    assert first.prev_hash is None
    assert second.prev_hash == first.row_hash


def test_next_hash_rejects_table_not_in_allowlist(pg_db) -> None:
    """Имя таблицы вне allowlist → ValueError (анти-SQL-инъекция по table_name)."""
    with pytest.raises(ValueError):
        next_hash(pg_db, "users; DROP TABLE access_events", {"x": 1})


def test_table_lock_key_is_deterministic_and_positive() -> None:
    """Ключ advisory-lock детерминирован и помещается в положительный int."""
    k1 = _table_lock_key("access_decisions")
    k2 = _table_lock_key("access_decisions")
    assert k1 == k2
    assert 0 <= k1 <= 0x7FFFFFFF
    assert _table_lock_key("access_events") != k1
