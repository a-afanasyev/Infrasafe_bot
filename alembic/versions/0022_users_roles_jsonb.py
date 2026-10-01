"""DB-049: ``users.roles`` TEXT → jsonb + GIN-индекс.

Роли хранились TEXT с JSON-строкой массива; фильтры по ролям были строковыми
(``LIKE '%"manager"%'``). Теперь jsonb, фильтр ``roles @> '["manager"]'``
(``database/roles_type.roles_contain``) под GIN ``jsonb_path_ops``.

Исторические формы значения нормализуются (как ``parse_roles_safe``):
JSON-массив — как есть; JSON-строка ``"manager"`` — в массив из одной роли;
CSV ``applicant,executor`` — в массив; пустое — NULL. Разбор во временной
функции (pg_temp), чтобы невалидный JSON не ронял миграцию, а уходил в CSV-ветку.

ALTER TYPE переписывает таблицу под ACCESS EXCLUSIVE — users небольшая
(сотни строк), блокировка короткая. Python-сторона не меняется: атрибут
``User.roles`` остаётся JSON-строкой (см. ``RolesJSON``).

Revision ID: 022
Revises: 021
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES_TO_JSONB_FN = r"""
CREATE OR REPLACE FUNCTION pg_temp.db049_roles_to_jsonb(v text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    j jsonb;
BEGIN
    IF v IS NULL OR btrim(v) = '' THEN
        RETURN NULL;
    END IF;
    BEGIN
        j := v::jsonb;
    EXCEPTION WHEN others THEN
        -- не JSON: CSV «applicant,executor»
        RETURN (
            SELECT jsonb_agg(btrim(x))
              FROM unnest(string_to_array(v, ',')) AS x
             WHERE btrim(x) <> ''
        );
    END;
    IF jsonb_typeof(j) = 'array' THEN
        RETURN j;
    END IF;
    IF jsonb_typeof(j) = 'string' AND btrim(j #>> '{}') <> '' THEN
        RETURN jsonb_build_array(btrim(j #>> '{}'));
    END IF;
    RETURN NULL;
END
$$;
"""

UPGRADE_STATEMENTS = (
    ROLES_TO_JSONB_FN,
    "ALTER TABLE users ALTER COLUMN roles TYPE jsonb USING pg_temp.db049_roles_to_jsonb(roles)",
    "CREATE INDEX ix_users_roles_gin ON users USING gin (roles jsonb_path_ops)",
)

DOWNGRADE_STATEMENTS = (
    "DROP INDEX IF EXISTS ix_users_roles_gin",
    # jsonb::text даёт тот же вид, что json.dumps: ["applicant", "executor"]
    "ALTER TABLE users ALTER COLUMN roles TYPE text USING roles::text",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
