"""DB-050/052 — guard query/FK indexes on the `requests` table.

The hot table `requests` is filtered by `status`, joined/filtered by `user_id`
and `executor_id`, and ordered by `created_at` (Kanban, analytics, assignment
lookups). Without indexes these are sequential scans that degrade as the table
grows. Migration 011 adds them; the ORM model declares `index=True` so a fresh
`create_all` (dev/CI bootstrap) stays in parity.

Structural sentinel (mirrors `test_apartment_fk_shape.py`): postgres-only,
skipped when `DATABASE_URL` is unset (the colocated sqlite suites don't carry a
pg catalog). Fails loudly if a future migration drops one of the indexes.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

EXPECTED_INDEXES = {
    "ix_requests_status",
    "ix_requests_user_id",
    "ix_requests_executor_id",
    "ix_requests_created_at",
}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — postgres-only test, skipping")
    return url


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_database_url(), future=True)
    yield eng
    eng.dispose()


def test_requests_query_indexes_present(engine):
    """pg_indexes snapshot — all four query/FK indexes must exist on `requests`."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'requests'")
        ).all()
    present = {r.indexname for r in rows}
    missing = EXPECTED_INDEXES - present
    assert not missing, (
        f"requests table is missing expected indexes {sorted(missing)} — "
        "migration 011 didn't run or was regressed. Present: "
        f"{sorted(present)}"
    )
