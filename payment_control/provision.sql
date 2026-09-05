\set ON_ERROR_STOP on
\getenv app_password PAYMENT_APP_PASSWORD
SELECT 'CREATE ROLE payment_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'payment_app') \gexec
SELECT format('ALTER ROLE payment_app PASSWORD %L', :'app_password') \gexec
GRANT CONNECT ON DATABASE payment_control TO payment_app;
GRANT USAGE ON SCHEMA public TO payment_app;
-- Точные права под фактические операции сервиса: импорты и журнал неизменяемы,
-- поэтому UPDATE есть только у payment_imports.status, а DELETE — только у
-- payment_claims (снимаются при деактивации). Журнал действий рантайм-роль
-- дописывать может, править и удалять — нет.
GRANT SELECT, INSERT, UPDATE ON payment_imports TO payment_app;
GRANT SELECT, INSERT ON payment_import_rows TO payment_app;
GRANT SELECT, INSERT, DELETE ON payment_claims TO payment_app;
GRANT SELECT, INSERT ON payment_audit TO payment_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO payment_app;
-- Новая таблица по умолчанию доступна только на чтение и вставку: расширять
-- права под неё нужно осознанно, отдельной строкой выше.
ALTER DEFAULT PRIVILEGES FOR ROLE payment_owner IN SCHEMA public
  GRANT SELECT, INSERT ON TABLES TO payment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE payment_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO payment_app;
