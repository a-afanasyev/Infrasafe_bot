"""ACL для parking_spots / parking_spot_assignments: гранты access_app_rw.

Обе таблицы созданы baseline'ом 0001 (строки 308+), но в ACL-массивы
`immut`/`other` той же миграции не попали — то есть `access_app_rw` не получила
на них НИЧЕГО, а бланкет-грант `uk_app_rw` (боту/API) не был отозван.
Практический эффект на проде: access-api ходит под `uk_access_runtime` →
`access_app_rw`, поэтому резидентский `GET /api/v1/access/my/spots`
(`access_control/api/resident.py:385`) и админские parking-эндпоинты
(`access_control/api/parking_admin.py`) отдавали 500 с
`InsufficientPrivilege: permission denied for table parking_spot_assignments`.

Отзыв бланкет-гранта `uk_app_rw` здесь НЕ делается: это ответственность
`uk_management_bot/dbops/acl_reconcile.py` (гоняется после КАЖДОГО
`alembic upgrade`, см. `scripts/entrypoint-migrate.sh`) — обе таблицы
добавлены в его `ACCESS_DOMAIN_TABLES` этим же изменением. Здесь — только
выдача прав, ровно как в baseline.

Sequences выдаются отдельно от таблиц: 4 из 22 access-domain таблиц имеют
`id` как serial-default (`autoincrement=True`), а не native identity, поэтому
INSERT'у нужен USAGE на backing-sequence. Две из них (`parking_spots`,
`parking_spot_assignments`) без грантов вообще, а у `access_entry_confirmations`
и `vehicle_presence_sessions` гранты на ТАБЛИЦЫ есть с baseline, но USAGE на
их sequences `access_app_rw` не выдавался никогда — при этом acl_reconcile
отзывает эти sequences у `uk_app_rw`, так что INSERT в них сегодня невозможен
ни одной runtime-роли. Сейчас это дремлющий дефект (INSERT-путей в коде для
них нет — только чтение в `access_control/repositories/presence_repo.py`), но
закрывается здесь же: то же семейство, та же одна строка SQL.

Revision ID: 007
Revises: 006
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Backing-sequences ищем через pg_depend (deptype IN ('a','i')), а не по шаблону
# "<table>_id_seq" — тот же приём и по той же причине, что в acl_reconcile.py и
# scripts/dba_ownership_transfer.sql: устойчиво к naming convention и к таблицам
# вовсе без sequence.
_SEQ_LOOP = """
        FOR seq IN
            SELECT DISTINCT sq.relname AS seq_name, t.relname AS table_name
            FROM pg_class t
            JOIN pg_depend d ON d.refobjid = t.oid AND d.deptype IN ('a', 'i')
            JOIN pg_class sq ON sq.oid = d.objid AND sq.relkind = 'S'
            WHERE t.relname = ANY(seq_tables)
        LOOP
"""


def upgrade() -> None:
    op.execute(
        """
    DO $$
    DECLARE
        -- SSOT: список access-domain таблиц продублирован в 0001 (immut/other),
        -- acl_reconcile.py (ACCESS_DOMAIN_TABLES) и dba_ownership_transfer.sql
        -- (excluded_tables). Гейт uk_management_bot/tests/test_access_domain_acl_ssot.py
        -- сверяет все три с __tablename__ моделей access_control/.
        other text[] := ARRAY['parking_spots','parking_spot_assignments'];
        -- + две serial-таблицы с baseline, чьи sequences остались без USAGE.
        seq_tables text[] := ARRAY['parking_spots','parking_spot_assignments',
            'access_entry_confirmations','vehicle_presence_sessions'];
        t text;
        seq RECORD;
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw') THEN
            RAISE NOTICE 'access_app_rw absent — parking ACL grants skipped';
            RETURN;
        END IF;
        FOREACH t IN ARRAY other LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO access_app_rw', t);
            END IF;
        END LOOP;
"""
        + _SEQ_LOOP
        + """
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO access_app_rw', seq.seq_name);
        END LOOP;
    END
    $$;
    """
    )


def downgrade() -> None:
    """Возврат к состоянию до 007: у access_app_rw прав нет, бланкет uk_app_rw цел.

    acl_reconcile на downgrade не гоняется, поэтому бланкет-грант `uk_app_rw`
    (который он снимает на upgrade-пути) восстанавливаем здесь явно — иначе
    downgrade оставил бы таблицы вообще без DML-ролей, а не в состоянии 006.
    """
    op.execute(
        """
    DO $$
    DECLARE
        other text[] := ARRAY['parking_spots','parking_spot_assignments'];
        seq_tables text[] := ARRAY['parking_spots','parking_spot_assignments',
            'access_entry_confirmations','vehicle_presence_sessions'];
        t text;
        seq RECORD;
        has_access boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw');
        has_app boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'uk_app_rw');
    BEGIN
        FOREACH t IN ARRAY other LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                IF has_access THEN
                    EXECUTE format('REVOKE ALL ON %I FROM access_app_rw', t);
                END IF;
                IF has_app THEN
                    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO uk_app_rw', t);
                END IF;
            END IF;
        END LOOP;
"""
        + _SEQ_LOOP
        + """
            IF has_access THEN
                EXECUTE format('REVOKE ALL ON SEQUENCE %I FROM access_app_rw', seq.seq_name);
            END IF;
            -- uk_app_rw возвращаем ТОЛЬКО на parking-sequences: у sequences
            -- access_entry_confirmations/vehicle_presence_sessions он был снят
            -- acl_reconcile'ом задолго до 007, восстанавливать нечего.
            IF has_app AND seq.table_name = ANY(other) THEN
                EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO uk_app_rw', seq.seq_name);
            END IF;
        END LOOP;
    END
    $$;
    """
    )
