"""DB-052 / DB-056 / DB-057 / DB-058 / DB-104 — sentinel для миграции 021.

Две части (по образцу test_db_perf_indexes_012):
* Статическая (бежит всегда): ни одна модель не объявляет PK c ``index=True``
  (DB-058 — дубль-индекс ``ix_<table>_id`` не должен вернуться через ORM).
* Pg-only структурная (skip без postgres DATABASE_URL): дубль-индексы сняты,
  FK-индексы есть, CHECK на outbox.status есть, board_config.data=jsonb,
  apartments.area=numeric.
"""
from __future__ import annotations

import os
import pathlib

import pytest
from sqlalchemy import create_engine, text

_MODELS_DIR = pathlib.Path(__file__).resolve().parents[1] / "database" / "models"


def test_no_pk_column_declares_redundant_index():
    """DB-058: PK-столбцы не должны иметь index=True (PK и так индексирован)."""
    offenders = []
    for path in _MODELS_DIR.glob("*.py"):
        if "primary_key=True, index=True" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert not offenders, (
        "PK-столбец с лишним index=True (DB-058) — дубль ix_<table>_id вернётся "
        f"через ORM create_all: {offenders}"
    )


# ── pg-only структурная часть ────────────────────────────────────────

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


def _index_names(engine, table: str) -> set[str]:
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": table}
        ).fetchall()
    return {r[0] for r in rows}


def test_redundant_pk_indexes_dropped(engine):
    # Выборочно: дубль-индексы на PK сняты (DB-058).
    for table in ("webhook_outbox", "requests", "ratings"):
        assert f"ix_{table}_id" not in _index_names(engine, table)


def test_fk_indexes_present(engine):
    # Выборочно: FK-индексы созданы (DB-052).
    assert "ix_ratings_user_id" in _index_names(engine, "ratings")
    assert "ix_request_assignments_executor_id" in _index_names(engine, "request_assignments")
    assert "ix_requests_assigned_by" in _index_names(engine, "requests")


def test_outbox_status_check_constraint(engine):
    with engine.connect() as c:
        found = c.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_webhook_outbox_status'")
        ).scalar()
    assert found, "DB-057: ck_webhook_outbox_status отсутствует"


def test_column_types_refined(engine):
    with engine.connect() as c:
        data_type = c.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='board_config' AND column_name='data'"
            )
        ).scalar()
        area_type = c.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='apartments' AND column_name='area'"
            )
        ).scalar()
    assert data_type == "jsonb", f"DB-056: board_config.data={data_type}, ожидался jsonb"
    assert area_type == "numeric", f"DB-104: apartments.area={area_type}, ожидался numeric"
