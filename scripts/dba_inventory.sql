-- PR-7 (F-01), Шаг 0 — read-only inventory. Запускать superuser/admin
-- credential'ом на КАЖДОМ проде ДО provisioning/ownership transfer, вывод
-- сохранить в verifier-log (без паролей). Ничего не создаёт и не меняет.

-- Роли: атрибуты, membership, возможность SET ROLE.
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin
FROM pg_roles
ORDER BY rolname;

SELECT gr.rolname AS granted_role, mr.rolname AS member_role, m.admin_option
FROM pg_auth_members m
JOIN pg_roles gr ON gr.oid = m.roleid
JOIN pg_roles mr ON mr.oid = m.member
ORDER BY 1, 2;

-- Владелец БД и схемы public.
SELECT d.datname, pg_catalog.pg_get_userbyid(d.datdba) AS owner
FROM pg_database d WHERE d.datname = current_database();

SELECT nspname, pg_catalog.pg_get_userbyid(nspowner) AS owner
FROM pg_namespace WHERE nspname = 'public';

-- Владельцы существующих объектов (tables/sequences/views/functions).
SELECT c.relkind, c.relname, pg_catalog.pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'S', 'v', 'm')
ORDER BY c.relkind, c.relname;

SELECT p.proname, pg_catalog.pg_get_userbyid(p.proowner) AS owner
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
ORDER BY p.proname;

-- Табличные/sequence/schema гранты — сверить с целевой ACL-матрицей
-- (immut/other/shared, см. план PR-7 §«Целевая ACL-матрица»).
SELECT grantee, table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privileges
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
GROUP BY grantee, table_name
ORDER BY grantee, table_name;

SELECT grantee, object_schema, object_name, object_type, privilege_type
FROM information_schema.usage_privileges
WHERE object_schema = 'public'
ORDER BY grantee, object_name;

-- pg_default_acl — default privileges, если уже настроены.
SELECT pg_catalog.pg_get_userbyid(d.defaclrole) AS owner_role, d.defaclnamespace::regnamespace AS schema,
       d.defaclobjtype, d.defaclacl
FROM pg_default_acl d;

-- Гранты PUBLIC (важно для schema-level USAGE carve-out).
SELECT nspname, nspacl FROM pg_namespace WHERE nspname = 'public';

-- Расширения и их владельцы.
SELECT extname, pg_catalog.pg_get_userbyid(extowner) AS owner FROM pg_extension;

-- Активные подключения — снять перед cutover (для понимания, что реально
-- держит открытые сессии на момент ownership transfer/quiesce).
SELECT pid, usename, application_name, client_addr, state, query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start;
