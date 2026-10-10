"""Охрана читает права из админки ролей: SELECT на rbac_* для access_app_rw.

ALTER DEFAULT PRIVILEGES роли миграций (scripts/dba_ownership_transfer.sql)
выдаёт новые таблицы только `uk_app_rw` (бот, API). access-api работает под
`uk_access_runtime` ∈ `access_app_rw` и без этого гранта не может прочитать
переопределения: `authz/store.py` оставался бы на правах из каталога, и правка
прав в админке до охраны не доходила бы. Охрана права только читает — пишет
их API, поэтому только SELECT.

Revision ID: 024
Revises: 023
Create Date: 2026-10-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Таблицы, которые читает `authz/store.py` в каждом процессе.
RBAC_TABLES = ("rbac_roles", "rbac_role_permissions", "rbac_state")


def _for_each_table(statement: str) -> str:
    tables = ",".join(f"'{t}'" for t in RBAC_TABLES)
    return f"""
    DO $$
    DECLARE
        t text;
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw') THEN
            RAISE NOTICE 'access_app_rw absent — rbac read grants skipped';
            RETURN;
        END IF;
        FOREACH t IN ARRAY ARRAY[{tables}] LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format('{statement}', t);
            END IF;
        END LOOP;
    END
    $$;
    """


def upgrade() -> None:
    op.execute(_for_each_table("GRANT SELECT ON %I TO access_app_rw"))


def downgrade() -> None:
    op.execute(_for_each_table("REVOKE SELECT ON %I FROM access_app_rw"))
