-- AUD6-P1-2: least-privilege роль для resource-accounting (рецидив PENT-F01,
-- закрытого PR-7 для основной БД: runtime-роль была ≡ миграционной ≡ владельцу).
--
-- Модель ролей выделенного инстанса uk-resource-postgres:
--   * `resource` (POSTGRES_USER) — суперпользователь инстанса, владелец БД и
--     всех объектов; под ним ходят ТОЛЬКО alembic-миграции + seed
--     (compose-сервис `resource-migrate`, profiles: ["tools"]).
--   * `resource_app` — runtime-роль сервисов resource-api / resource-worker:
--     DML + sequences, БЕЗ CREATE (на postgres:16 у PUBLIC его на schema
--     public и так нет — REVOKE ниже защищает от даунгрейда/наследия).
--
-- Запуск (под `resource`, идемпотентно; пароль НЕ инлайнится в SQL):
--   psql -v ON_ERROR_STOP=1 -v app_password='<из Doppler RESOURCE_APP_PASSWORD>' \
--        -f provision_resource_roles.sql
-- На проде — через compose-сервис resource-provision-roles (см. docker-compose*.yml);
-- процедура целиком — .claude/skills/uk-deploy/SKILL.md.
--
-- Этот файл — SSOT и для CI: джоба resource-tests исполняет ИМЕННО его, а затем
-- поведенчески проверяет «CREATE TABLE под resource_app падает, DML проходит».

\set ON_ERROR_STOP 1

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'resource_app') THEN
        CREATE ROLE resource_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

-- Пароль и атрибуты — безусловно (идемпотентный повтор = ротация пароля).
ALTER ROLE resource_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';

-- Подключение к текущей БД (скрипт запускается уже присоединённым к ней).
SELECT format('GRANT CONNECT ON DATABASE %I TO resource_app', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO resource_app;
-- Защита от наследия/даунгрейда: на PG15+ у обычных ролей CREATE на public и
-- так нет, но полагаться на дефолт образа — значит сломаться молча при его смене.
REVOKE CREATE ON SCHEMA public FROM resource_app;

-- Существующие объекты (все созданы владельцем `resource`).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO resource_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO resource_app;

-- Будущие объекты: миграции гоняет ТОЛЬКО `resource` (resource-migrate), поэтому
-- default privileges от его имени покрывают каждую новую таблицу/sequence — новая
-- миграция не требует ручного до-гранта (грабля parking_spots из аудита #6 здесь
-- невозможна по построению).
ALTER DEFAULT PRIVILEGES FOR ROLE resource IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO resource_app;
ALTER DEFAULT PRIVILEGES FOR ROLE resource IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO resource_app;
