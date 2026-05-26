"""set ON DELETE SET NULL on requests.apartment_id FK (FIX-003 / DB-111)

Purge yard/building падал на FK violation, потому что
`requests.apartment_id -> apartments.id` имела действие ON DELETE NO ACTION.

**DB-111 prod-safe rewrite (3-step pattern).** Прежняя версия делала
`DROP CONSTRAINT` + `ADD CONSTRAINT` под `ACCESS EXCLUSIVE` lock — на live
`requests` (>100k rows) это full table lock + scan = реальный outage. Новая
схема использует Postgres-специфичный `NOT VALID` + `VALIDATE` чтобы
тяжёлый шаг сканирования брал только `SHARE UPDATE EXCLUSIVE` lock
(concurrent reads + non-DDL writes допустимы).

Шаги (upgrade, в Postgres):
  1. `ADD CONSTRAINT requests_apartment_id_fkey_v2 ... ON DELETE SET NULL NOT VALID`
     — instant, только pg_constraint update; enforcing новых INSERT/UPDATE
       начинается сразу.
  2. `DROP CONSTRAINT requests_apartment_id_fkey` — instant; единственный
     enforcer теперь — _v2 c корректной SET NULL семантикой. Окно «никакой
     FK» отсутствует: к этому моменту _v2 уже активен на write-path.
  3. `VALIDATE CONSTRAINT requests_apartment_id_fkey_v2` — `SHARE UPDATE
     EXCLUSIVE` lock, scans table; concurrent reads + non-DDL writes
     продолжают работать; параллельные ALTER TABLE / другие VALIDATE
     блокируются. На прод-данных без orphan-refs (что гарантировано
     предшествующим NO ACTION FK) — всегда успешно.
  4. `RENAME CONSTRAINT _v2 -> requests_apartment_id_fkey` — instant,
     косметика (имя совпадает со старым, чтобы downstream tooling и
     auto-generated alembic diff не путались).

Для SQLite/in-memory test engines fallback на простой DROP+ADD — `NOT
VALID`/`VALIDATE` Postgres-specific, а concerns по locking в test engine
неактуальны.

Тест-наблюдение (manual, prod-deploy time, см. AC DB-111):
  ```sql
  -- В отдельной psql сессии во время `alembic upgrade head`:
  SELECT mode, granted, query_start, NOW() - query_start AS held
  FROM pg_locks l JOIN pg_stat_activity a USING (pid)
  WHERE l.relation = 'requests'::regclass;
  -- AccessExclusiveLock не должен держаться дольше 100 ms (только на
  -- instant-ные ADD/DROP/RENAME). VALIDATE должен показывать
  -- ShareUpdateExclusiveLock.
  ```

Revision ID: 007
Revises: 006
Create Date: 2026-05-21 (rewritten 2026-05-27 per DB-111)
"""
from typing import Sequence, Union

from alembic import op

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Имя FK подтверждено через pg_constraint:
#   conname = 'requests_apartment_id_fkey'
CONSTRAINT_NAME = 'requests_apartment_id_fkey'
CONSTRAINT_NAME_V2 = 'requests_apartment_id_fkey_v2'
SOURCE_TABLE = 'requests'
TARGET_TABLE = 'apartments'
LOCAL_COL = 'apartment_id'
REMOTE_COL = 'id'


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgres():
        # Test engines (SQLite/in-memory) — locking concerns moot, do
        # the straightforward DROP+ADD instead. Postgres-only NOT VALID
        # syntax would error out here.
        op.drop_constraint(CONSTRAINT_NAME, SOURCE_TABLE, type_='foreignkey')
        op.create_foreign_key(
            CONSTRAINT_NAME,
            SOURCE_TABLE,
            TARGET_TABLE,
            [LOCAL_COL],
            [REMOTE_COL],
            ondelete='SET NULL',
        )
        return

    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} "
        f"ADD CONSTRAINT {CONSTRAINT_NAME_V2} "
        f"FOREIGN KEY ({LOCAL_COL}) REFERENCES {TARGET_TABLE} ({REMOTE_COL}) "
        f"ON DELETE SET NULL NOT VALID"
    )
    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} DROP CONSTRAINT {CONSTRAINT_NAME}"
    )
    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} VALIDATE CONSTRAINT {CONSTRAINT_NAME_V2}"
    )
    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} "
        f"RENAME CONSTRAINT {CONSTRAINT_NAME_V2} TO {CONSTRAINT_NAME}"
    )


def downgrade() -> None:
    """Reverse — same 3-step pattern, восстанавливая исходный NO ACTION."""
    if not _is_postgres():
        op.drop_constraint(CONSTRAINT_NAME, SOURCE_TABLE, type_='foreignkey')
        op.create_foreign_key(
            CONSTRAINT_NAME,
            SOURCE_TABLE,
            TARGET_TABLE,
            [LOCAL_COL],
            [REMOTE_COL],
            # No ondelete clause = NO ACTION (original behaviour).
        )
        return

    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} "
        f"ADD CONSTRAINT {CONSTRAINT_NAME_V2} "
        f"FOREIGN KEY ({LOCAL_COL}) REFERENCES {TARGET_TABLE} ({REMOTE_COL}) "
        f"NOT VALID"
    )
    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} DROP CONSTRAINT {CONSTRAINT_NAME}"
    )
    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} VALIDATE CONSTRAINT {CONSTRAINT_NAME_V2}"
    )
    op.execute(
        f"ALTER TABLE {SOURCE_TABLE} "
        f"RENAME CONSTRAINT {CONSTRAINT_NAME_V2} TO {CONSTRAINT_NAME}"
    )
