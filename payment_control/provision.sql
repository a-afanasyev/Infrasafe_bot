\set ON_ERROR_STOP on
\getenv app_password PAYMENT_APP_PASSWORD
SELECT 'CREATE ROLE payment_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'payment_app') \gexec
SELECT format('ALTER ROLE payment_app PASSWORD %L', :'app_password') \gexec
GRANT CONNECT ON DATABASE payment_control TO payment_app;
GRANT USAGE ON SCHEMA public TO payment_app;
-- Скрипт выполняется при инициализации пустого тома, когда таблиц ещё нет
-- (их создаёт payment-migrate позже). Поэтому здесь только то, что не зависит
-- от существования таблиц: базовые права «читать и дописывать» для будущих
-- таблиц через ALTER DEFAULT PRIVILEGES. Точные UPDATE/DELETE под фактические
-- операции сервиса выдаёт миграция payment_001 сразу после создания таблиц —
-- гранты по именам таблиц здесь оборвали бы скрипт на первой же строке.
ALTER DEFAULT PRIVILEGES FOR ROLE payment_owner IN SCHEMA public
  GRANT SELECT, INSERT ON TABLES TO payment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE payment_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO payment_app;
-- Идемпотентно: повторный запуск (ротация пароля) добивает права и на уже
-- существующие таблицы, ничего не ломая.
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO payment_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO payment_app;
