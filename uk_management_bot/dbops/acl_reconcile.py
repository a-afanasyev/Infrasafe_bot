"""Post-migration ACL-reconciliation helper (PR-7 / F-01).

Две реконсиляции, обе — компенсация побочного эффекта
``ALTER DEFAULT PRIVILEGES FOR ROLE uk_migration_owner ... TO uk_app_rw``
(см. план, «Provisioning и ownership»), которая применяется КО ВСЕМ таблицам,
созданным ПОСЛЕ момента её объявления — включая на fresh-install саму
baseline-миграцию (`alembic_version` и все 25 access-domain-таблиц создаются
ПОСЛЕ dba_ownership_transfer.sql, то есть уже ПОД действием этого
default-privilege, а не до него):

1. ``alembic_version`` carve-out (SELECT-only) — без него ``uk_app_rw``
   получила бы INSERT/UPDATE/DELETE наравне с обычной прикладной таблицей, и
   runtime (`uk_bot_runtime`/`uk_api_runtime`) мог бы подделать записанную
   ревизию, обойдя ``db_preflight``.
2. Access-domain (immut+other, 20 таблиц из ``0001_prc05_initial_baseline.py``)
   — явный REVOKE блáнкет-DML у ``uk_app_rw``. На проде (существующая БД)
   default privileges retroactively эти таблицы не задевают (они старше
   ownership-transfer), поэтому там это no-op; на fresh-install без этого шага
   бот/API получили бы полный CRUD на access-домен через членство в
   ``uk_app_rw`` — в обход собственной ACL-модели ``access_app_rw`` из
   миграции 0001. Идемпотентно и безопасно на каждом прогоне в обоих сценариях.
   ВКЛЮЧАЕТ backing-sequences этих таблиц (identity/serial PK — например
   ``access_events_id_seq``), найденные через ``pg_depend``, а не по имени:
   ``ALTER DEFAULT PRIVILEGES ... ON SEQUENCES`` бланкет-грантит их точно так
   же, как таблицы, и без явного revoke ``uk_app_rw`` сохраняла бы
   ``nextval()``/``currval()``/``last_value`` на audit-sequences — утечка
   объёма событий в обход table-level ACL, независимо от того, что сам
   table-level REVOKE уже применён.

Вызывается только из `entrypoint-migrate.sh`, ПОСЛЕ `alembic upgrade head`.
Подключается тем же credential'ом, что и Alembic (`uk_migrator`) — поэтому,
как и `alembic/env.py`, обязан сам переключиться на `uk_migration_owner` через
`SET SESSION ROLE`, иначе REVOKE/GRANT ниже упадут `permission denied`
(`uk_migrator` — NOINHERIT, не пользуется привилегиями owner'а автоматически).
"""
import os
import sys

from sqlalchemy import create_engine, pool, text

# Гейт идентичен alembic/env.py: там, где uk_migration_owner ещё не
# провижинена (dev/CI без provision-roles), helper — no-op, не ошибка.
# Там, где роль обязана быть (REQUIRE_MIGRATION_OWNER=1 — прод migrate-job,
# новый PostgreSQL least-privilege CI job), отсутствие роли — явная ошибка.

# Те же 20 access-domain таблиц (immut+other), что в
# alembic/versions/0001_prc05_initial_baseline.py:1298-1337 — только имена,
# без разбивки на immut/other: обеим подгруппам одинаково не место в
# блáнкет-гранте uk_app_rw, у них своя ACL через access_app_rw.
ACCESS_DOMAIN_TABLES = [
    "access_events", "access_decisions", "manual_openings", "access_audit_logs",
    "parking_zones", "parking_zone_yards", "access_gates", "access_cameras",
    "access_barriers", "edge_controllers", "vehicles", "vehicle_apartments",
    "access_rules", "access_passes", "resident_access_requests", "camera_events",
    "controller_sync_events", "barrier_commands", "access_entry_confirmations",
    "vehicle_presence_sessions",
]

# Находит backing-sequences access-domain таблиц через pg_depend, а не по
# имени: устойчиво к любой naming convention и к таблицам без sequence (UUID PK).
# deptype IN ('a', 'i') — ОБЯЗАТЕЛЬНО оба, не только 'a'. 'a' (auto) — классический
# SERIAL/BIGSERIAL; 'i' (internal) — нативная identity-колонка (GENERATED ... AS
# IDENTITY), которую использует 17 из 20 access-domain таблиц в этой миграции.
# Фильтр только по 'a' эмпирически подтверждён неверным: находит sequences лишь
# у 2 из 20 таблиц и пропускает access_events_id_seq и ещё 16 — оставляя их
# блáнкет-грант uk_app_rw неотозванным (та самая утечка, которую эта функция
# должна закрывать).
_SEQUENCES_FOR_TABLES_SQL = """
    SELECT DISTINCT s.relname
    FROM pg_class t
    JOIN pg_depend d ON d.refobjid = t.oid AND d.deptype IN ('a', 'i')
    JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
    WHERE t.relname = ANY(:tables)
"""


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("acl_reconcile: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    require_owner = os.getenv("REQUIRE_MIGRATION_OWNER") == "1"

    # NullPool — как в alembic/env.py: SET SESSION ROLE — session-scoped, не
    # должен пережить эту функцию и вернуться в пул на переиспользование.
    # Сегодня этот скрипт делает только один connect(), поэтому пока не
    # наблюдаемо, но защита от будущего расширения дешевле, чем полагаться
    # на дисциплину call-site.
    engine = create_engine(database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            owner_exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = 'uk_migration_owner'")
            ).scalar()

            if not owner_exists:
                if require_owner:
                    print(
                        "acl_reconcile: REQUIRE_MIGRATION_OWNER=1, но роль "
                        "uk_migration_owner не найдена — provisioning не завершён",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                print("acl_reconcile: uk_migration_owner not provisioned — skipping (dev/CI)")
                return

            conn.execute(text("SET SESSION ROLE uk_migration_owner"))

            conn.execute(
                text(
                    "REVOKE INSERT, UPDATE, DELETE ON alembic_version "
                    "FROM uk_app_rw, access_app_rw"
                )
            )
            conn.execute(text("GRANT SELECT ON alembic_version TO uk_app_rw, access_app_rw"))

            # Только существующие таблицы (to_regclass) — на самой первой
            # миграции до создания access-домена REVOKE на несуществующую
            # таблицу упал бы, а не no-op'нул.
            for table in ACCESS_DOMAIN_TABLES:
                exists = conn.execute(
                    text("SELECT to_regclass('public.' || :t) IS NOT NULL"), {"t": table}
                ).scalar()
                if exists:
                    conn.execute(text(f'REVOKE ALL ON "{table}" FROM uk_app_rw'))

            # Их sequences — тот же default-privilege leak, что и таблицы (см.
            # docstring п.2), но sequences не совпадают по имени с таблицей, их
            # нужно находить отдельно через pg_depend, не по шаблону "<table>_id_seq".
            seq_rows = conn.execute(
                text(_SEQUENCES_FOR_TABLES_SQL), {"tables": ACCESS_DOMAIN_TABLES}
            ).fetchall()
            for (seq_name,) in seq_rows:
                conn.execute(text(f'REVOKE ALL ON "{seq_name}" FROM uk_app_rw'))

            conn.commit()
            print(
                "acl_reconcile: alembic_version carve-out + access-domain "
                "uk_app_rw revoke applied"
            )
    except Exception as exc:  # noqa: BLE001 — fail-closed: любая ошибка здесь останавливает deploy
        print(f"acl_reconcile: failed: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
