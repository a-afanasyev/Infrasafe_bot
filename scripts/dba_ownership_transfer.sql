-- PR-7 (F-01) — DBA rollout: ownership transfer + default privileges + schema
-- USAGE carve-out. Запускать ВРУЧНУЮ, superuser/admin credential'ом, ТОЛЬКО
-- внутри согласованного maintenance-окна, ПОСЛЕ scripts/provision_roles.sql
-- (роль uk_migration_owner должна уже существовать) и ПОСЛЕ quiesce
-- bot/api/access-api (см. план PR-7, «Deploy flow», шаги 4-5) — иначе старые
-- контейнеры, ещё подключённые под прежней ролью-владельцем, начнут получать
-- permission denied сразу после COMMIT этого скрипта, а не в запланированный
-- момент cutover.
--
-- НЕ идемпотентно в общем смысле «безопасно гонять на каждом деплое» — это
-- одноразовый (per-cutover) shift владения. Безопасно повторить: ALTER ...
-- OWNER TO на объекте, уже принадлежащем uk_migration_owner, — no-op.

BEGIN;

-- Владелец БД и схемы public. ALTER DATABASE требует литеральный identifier,
-- не expression — current_database() подставляется через EXECUTE format().
DO $$
BEGIN
  EXECUTE format('ALTER DATABASE %I OWNER TO uk_migration_owner', current_database());
END
$$;
ALTER SCHEMA public OWNER TO uk_migration_owner;

-- Все существующие таблицы/views/materialized views/функции в public —
-- независимо от того, кто был владельцем (uk_bot и т.п.). Ownership transfer
-- НЕ меняет уже выданные GRANT/REVOKE (access_app_rw ACL на immut/other/shared
-- остаётся как есть, см. миграцию 0001_prc05_initial_baseline).
--
-- Sequences (relkind='S') НЕ включены в этот цикл и не должны быть: emпирически
-- подтверждено на проде (profk, 2026-07-15) — PostgreSQL запрещает прямой
-- `ALTER SEQUENCE ... OWNER TO` для sequence, связанной с таблицей через
-- serial/identity-колонку (`ERROR: cannot change owner of sequence "X" —
-- Sequence "X" is linked to table "Y"`), и в этой схеме ВСЕ 53 sequences
-- линкованы (проверено запросом к pg_depend, deptype IN ('a','i') — 0
-- standalone). Владение linked-sequence меняется АВТОМАТИЧЕСКИ как побочный
-- эффект `ALTER TABLE ... OWNER TO` на владеющей таблице — отдельный шаг не
-- нужен и físически невозможен для этого набора объектов.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT c.relkind, c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm')
  LOOP
    CASE r.relkind
      WHEN 'r' THEN EXECUTE format('ALTER TABLE public.%I OWNER TO uk_migration_owner', r.relname);
      WHEN 'v' THEN EXECUTE format('ALTER VIEW public.%I OWNER TO uk_migration_owner', r.relname);
      WHEN 'm' THEN EXECUTE format('ALTER MATERIALIZED VIEW public.%I OWNER TO uk_migration_owner', r.relname);
    END CASE;
  END LOOP;

  FOR r IN
    SELECT p.oid::regprocedure::text AS signature
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
  LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO uk_migration_owner', r.signature);
  END LOOP;
END
$$;

-- Bulk-грант на УЖЕ СУЩЕСТВУЮЩИЕ (на момент этого cutover) не-access-domain
-- таблицы/sequences — обязателен ОТДЕЛЬНО от ALTER DEFAULT PRIVILEGES ниже.
-- ALTER DEFAULT PRIVILEGES действует ТОЛЬКО на объекты, созданные ПОСЛЕ него —
-- без этого явного bulk-гранта uk_bot_runtime/uk_api_runtime получили бы
-- `permission denied` на КАЖДОЙ уже существующей UK-таблице (users, requests,
-- shifts и т.д.) сразу после cutover: раньше их обслуживало владение объектом
-- (uk_bot был owner), а голого GRANT'а этим таблицам никогда не выдавалось.
-- access-domain-таблицы (immut+other, 20 шт.) исключены явно — у них
-- собственная ACL-модель из access_app_rw (миграция 0001), uk_app_rw там
-- доступа иметь не должен. alembic_version тоже исключена — её carve-out
-- (SELECT-only) применяет uk_management_bot/dbops/acl_reconcile.py.
--
-- Критично: исключение по ИМЕНИ таблицы недостаточно для sequences — 19 из
-- 20 access-domain таблиц используют identity/serial PK с backing-sequence
-- (`access_events_id_seq` и т.п.), которая как отдельный объект (`relkind='S'`)
-- никогда не совпадёт по имени с именем таблицы в exclusion-массиве. Без
-- явного исключения bulk-грант отдаёт `uk_app_rw` USAGE+SELECT на эти
-- sequences — nextval()/currval()/last_value читаемы боту/API в обход
-- table-level ACL, утечка объёма событий из access-домена и риск порчи PK
-- через setval() скомпрометированным bot/api credential. Поэтому sequences
-- исключаются не по имени, а через pg_depend (кто реально владеет этой
-- sequence как serial/identity-колонкой таблицы) — устойчиво к любому
-- naming convention и к UUID/иным PK-типам, где sequence может не быть вовсе.
DO $$
DECLARE
  excluded_tables text[] := ARRAY[
    -- immut (4)
    'access_events','access_decisions','manual_openings','access_audit_logs',
    -- other (16)
    'parking_zones','parking_zone_yards','access_gates','access_cameras',
    'access_barriers','edge_controllers','vehicles','vehicle_apartments','access_rules',
    'access_passes','resident_access_requests','camera_events','controller_sync_events',
    'barrier_commands','access_entry_confirmations','vehicle_presence_sessions'
  ];
  excluded_relnames text[];
  r RECORD;
BEGIN
  -- excluded_relnames = имена таблиц + имена ИХ sequences (через pg_depend) +
  -- alembic_version (не access-domain, но carve-out для неё — отдельная
  -- ответственность acl_reconcile.py, не этого bulk-гранта).
  --
  -- КРИТИЧНО: deptype IN ('a', 'i'), НЕ только 'a'. 'a' (auto) — зависимость
  -- классического SERIAL/BIGSERIAL (CREATE SEQUENCE + ALTER SEQUENCE ...
  -- OWNED BY). 'i' (internal) — зависимость нативной identity-колонки
  -- (GENERATED ... AS IDENTITY), которую использует 17 из 20 access-domain
  -- таблиц в этой миграции (sa.Identity() в моделях — не autoincrement=True).
  -- Единственный фильтр по 'a' эмпирически проверен и подтверждён неверным:
  -- находит sequences только у 2 из 20 таблиц (access_entry_confirmations,
  -- vehicle_presence_sessions — единственные на голом autoincrement=True), и
  -- молча пропускает остальные 17, включая access_events_id_seq — именно ту
  -- sequence, что приведена как пример в комментариях этого файла. С фильтром
  -- только 'a' bulk-грант ниже продолжал бы выдавать uk_app_rw USAGE+SELECT
  -- на все 17 пропущенных sequences — воспроизводя ту самую утечку, которую
  -- этот блок должен закрывать.
  SELECT array_agg(DISTINCT x) INTO excluded_relnames
  FROM (
    SELECT unnest(excluded_tables) AS x
    UNION
    SELECT 'alembic_version'
    UNION
    SELECT s.relname
    FROM pg_class t
    JOIN pg_depend d ON d.refobjid = t.oid AND d.deptype IN ('a', 'i')
    JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
    WHERE t.relname = ANY(excluded_tables)
  ) sub;

  FOR r IN
    SELECT c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'S')
      AND NOT (c.relname = ANY(excluded_relnames))
  LOOP
    IF r.relkind = 'r' THEN
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO uk_app_rw', r.relname);
    ELSE
      EXECUTE format('GRANT USAGE, SELECT ON public.%I TO uk_app_rw', r.relname);
    END IF;
  END LOOP;
END
$$;

-- Default privileges для роли, под которой Alembic (после SET SESSION ROLE)
-- будет создавать НОВЫЕ объекты — применяется только к объектам, созданным
-- ПОСЛЕ этого момента. На fresh-install это означает, что baseline-миграция
-- (запускается ПОСЛЕ этого cutover-скрипта) создаст 25 access-domain таблиц
-- УЖЕ под действием этого default-privilege — они бы тоже получили блáнкет
-- uk_app_rw грант, что неверно (см. «Целевая ACL-матрица» в плане PR-7).
-- Компенсация — uk_management_bot/dbops/acl_reconcile.py явно REVOKE'ит
-- uk_app_rw с access-domain таблиц после КАЖДОГО migrate (fresh-install и
-- прод одинаково, идемпотентно).
ALTER DEFAULT PRIVILEGES FOR ROLE uk_migration_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO uk_app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE uk_migration_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO uk_app_rw;

-- Schema-level USAGE carve-out: PostgreSQL по умолчанию даёт USAGE на public
-- псевдо-роли PUBLIC — REVOKE ALL убирает implicit-доступ, компенсирующий
-- GRANT USAGE восстанавливает его явно для реальных группа-ролей.
-- uk_migration_owner не нуждается в отдельном GRANT (владелец схемы).
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO uk_app_rw, access_app_rw;

COMMIT;

-- После COMMIT — carve-out на alembic_version (SELECT-only для uk_app_rw/
-- access_app_rw) применяет scripts/entrypoint-migrate.sh через
-- uk_management_bot/dbops/acl_reconcile.py на первом же прогоне `migrate`,
-- НЕ этот скрипт (alembic_version уже существует до PR-7, но именно
-- acl_reconcile — единственное место, которое переиздаёт carve-out после
-- КАЖДОЙ будущей миграции, а не только один раз при cutover).
