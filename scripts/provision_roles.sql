-- PR-7 (F-01): единый provisioning-скрипт целевой модели ролей.
-- Используется ОДИНАКОВО для fresh-install и для DBA rollout на существующем
-- проде. Идемпотентен: создание ролей — только при отсутствии, атрибуты/
-- membership/пароли — переприменяются и реконсилируются на КАЖДОМ прогоне.
--
-- Вызывается через scripts/provision_roles.sh, который передаёт пароли как
-- psql-переменные (-v migrator_pw=... и т.д.) — подстановка :'var' работает
-- ТОЛЬКО вне dollar-quoted DO $$...$$ блоков, поэтому ALTER ROLE ... PASSWORD
-- вынесен отдельными top-level операторами в конец файла.

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='uk_migration_owner') THEN
    CREATE ROLE uk_migration_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='uk_app_rw') THEN
    CREATE ROLE uk_app_rw NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='access_app_rw') THEN
    CREATE ROLE access_app_rw NOLOGIN;  -- обычно уже создана B0-гейтом/PRC-05, guard на случай отсутствия
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='uk_migrator') THEN
    CREATE ROLE uk_migrator LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='uk_bot_runtime') THEN
    CREATE ROLE uk_bot_runtime LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='uk_api_runtime') THEN
    CREATE ROLE uk_api_runtime LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='uk_access_runtime') THEN
    CREATE ROLE uk_access_runtime LOGIN;
  END IF;
END
$$;

-- На КАЖДОМ прогоне — переприменить опасные атрибуты (защита от ручного дрейфа).
ALTER ROLE uk_migration_owner NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN NOINHERIT;
ALTER ROLE uk_app_rw          NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN NOINHERIT;
ALTER ROLE access_app_rw      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN NOINHERIT;
ALTER ROLE uk_migrator        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS LOGIN NOINHERIT;
ALTER ROLE uk_bot_runtime     NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS LOGIN INHERIT;
ALTER ROLE uk_api_runtime     NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS LOGIN INHERIT;
ALTER ROLE uk_access_runtime  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS LOGIN INHERIT;

-- Memberships — конвергентная реконсиляция, не просто additive GRANT.
-- 1) Снять ADMIN OPTION, если она когда-либо была выдана (идемпотентно).
REVOKE ADMIN OPTION FOR uk_migration_owner FROM uk_migrator;
REVOKE ADMIN OPTION FOR uk_app_rw          FROM uk_bot_runtime;
REVOKE ADMIN OPTION FOR uk_app_rw          FROM uk_api_runtime;
REVOKE ADMIN OPTION FOR access_app_rw      FROM uk_access_runtime;

-- 2) Двунаправленная реконсиляция: и "у LOGIN-ролей нет лишних memberships",
--    и "у owner/group-ролей нет посторонних членов". Имена берутся из
--    pg_roles.rolname напрямую (не через ::regrole::text — тот уже цитирует
--    идентификатор, повторное цитирование в format('%I', ...) задвоило бы кавычки).
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT gr.rolname AS granted_role,
           mr.rolname AS member_role
    FROM pg_auth_members m
    JOIN pg_roles gr ON gr.oid = m.roleid
    JOIN pg_roles mr ON mr.oid = m.member
    WHERE mr.rolname IN
          ('uk_migrator','uk_bot_runtime','uk_api_runtime','uk_access_runtime')
  LOOP
    IF NOT (
      (r.member_role = 'uk_migrator'       AND r.granted_role = 'uk_migration_owner') OR
      (r.member_role = 'uk_bot_runtime'    AND r.granted_role = 'uk_app_rw') OR
      (r.member_role = 'uk_api_runtime'    AND r.granted_role = 'uk_app_rw') OR
      (r.member_role = 'uk_access_runtime' AND r.granted_role = 'access_app_rw')
    ) THEN
      EXECUTE format('REVOKE %I FROM %I', r.granted_role, r.member_role);
    END IF;
  END LOOP;

  FOR r IN
    SELECT gr.rolname AS granted_role,
           mr.rolname AS member_role
    FROM pg_auth_members m
    JOIN pg_roles gr ON gr.oid = m.roleid
    JOIN pg_roles mr ON mr.oid = m.member
    WHERE gr.rolname IN
          ('uk_migration_owner','uk_app_rw','access_app_rw')
  LOOP
    IF NOT (
      (r.granted_role = 'uk_migration_owner' AND r.member_role = 'uk_migrator') OR
      (r.granted_role = 'uk_app_rw'          AND r.member_role IN ('uk_bot_runtime','uk_api_runtime')) OR
      (r.granted_role = 'access_app_rw'      AND r.member_role = 'uk_access_runtime')
    ) THEN
      EXECUTE format('REVOKE %I FROM %I', r.granted_role, r.member_role);
    END IF;
  END LOOP;

  -- 3-я, ранее пропущенная директория реконсиляции: НИКТО не должен быть
  -- членом ни одной из 4 LOGIN-ролей (uk_migrator и т.д.) — ни одна из первых
  -- двух проверок этого не ловит: цикл выше фильтрует mr (member) IN 4
  -- login-ролей — не видит строку, где сама login-роль выступает GRANTED
  -- (gr.rolname), а членом (mr) стал кто-то посторонний. Пример дыры: `GRANT
  -- uk_migrator TO some_other_role` делает some_other_role способной SET ROLE
  -- uk_migrator → transitively uk_migration_owner (владелец схемы) — полная
  -- эскалация в обход всей модели. Легитимных членов у LOGIN-ролей нет
  -- вообще (никто не должен наследовать/переключаться на uk_migrator и т.п.
  -- кроме самой этой роли при подключении), поэтому revoke безусловный.
  FOR r IN
    SELECT gr.rolname AS granted_role,
           mr.rolname AS member_role
    FROM pg_auth_members m
    JOIN pg_roles gr ON gr.oid = m.roleid
    JOIN pg_roles mr ON mr.oid = m.member
    WHERE gr.rolname IN
          ('uk_migrator','uk_bot_runtime','uk_api_runtime','uk_access_runtime')
  LOOP
    EXECUTE format('REVOKE %I FROM %I', r.granted_role, r.member_role);
  END LOOP;
END
$$;

-- 3) Выдать ИМЕННО целевые memberships (идемпотентно, без ADMIN OPTION).
GRANT uk_migration_owner TO uk_migrator;
GRANT uk_app_rw          TO uk_bot_runtime;
GRANT uk_app_rw          TO uk_api_runtime;
GRANT access_app_rw      TO uk_access_runtime;

-- Пароли — вне DO, top-level, psql подставляет :'var' нормально.
ALTER ROLE uk_migrator       PASSWORD :'migrator_pw';
ALTER ROLE uk_bot_runtime    PASSWORD :'bot_pw';
ALTER ROLE uk_api_runtime    PASSWORD :'api_pw';
ALTER ROLE uk_access_runtime PASSWORD :'access_pw';

COMMIT;
