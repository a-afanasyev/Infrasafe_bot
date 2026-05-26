"""DB-111 — guard the shape of `requests.apartment_id` FK.

`requests_apartment_id_fkey` must:
  * have `ON DELETE SET NULL` (`confdeltype = 'n'`)
  * be validated (`convalidated = 't'`)
  * reference `apartments.id`
  * keep the canonical name `requests_apartment_id_fkey` (so the prod-safe
    3-step migration's RENAME step is the final state, not the intermediate
    `_v2` constraint).

End-state behaviour is covered by `test_apartment_purge.py`. This file is
a *structural* sentinel — if a future migration accidentally regresses the
shape (e.g. switches back to NO ACTION, or leaves the constraint
unvalidated, or drops the constraint entirely) it will fail loudly here
before anyone gets to the slower behavioural test.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


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


def test_apartment_fk_has_set_null_and_is_validated(engine):
    """pg_constraint snapshot of `requests_apartment_id_fkey`."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT c.conname,
                       c.confdeltype,
                       c.convalidated,
                       conf.relname AS referenced_table,
                       att.attname  AS referenced_column
                FROM pg_constraint c
                JOIN pg_class src   ON src.oid = c.conrelid
                JOIN pg_class conf  ON conf.oid = c.confrelid
                JOIN pg_attribute att
                  ON att.attrelid = c.confrelid AND att.attnum = ANY (c.confkey)
                WHERE src.relname = 'requests'
                  AND c.conname = 'requests_apartment_id_fkey'
                """
            )
        ).first()

    assert row is not None, (
        "FK requests_apartment_id_fkey not found — DB-111 migration "
        "either didn't run or left the constraint under its intermediate "
        "_v2 name (missed RENAME step)"
    )
    # 'n' = SET NULL. 'a' = NO ACTION (original, pre-FIX-003 behaviour).
    assert row.confdeltype == "n", (
        f"FK confdeltype is {row.confdeltype!r} — expected 'n' (SET NULL); "
        "the FIX-003 migration was not applied or has been regressed."
    )
    assert row.convalidated is True, (
        "FK is not validated — the prod-safe 3-step migration must run "
        "VALIDATE CONSTRAINT after ADD ... NOT VALID."
    )
    assert row.referenced_table == "apartments"
    assert row.referenced_column == "id"
