-- UK Management Bot — PostgreSQL Init Script
-- Runs as superuser via /docker-entrypoint-initdb.d/
--
-- The postgres:15-alpine image ALREADY creates:
--   - Database: $POSTGRES_DB
--   - User: $POSTGRES_USER with $POSTGRES_PASSWORD
-- This script only sets up extensions and default privileges.
-- Schema/tables are managed by Alembic migrations (API entrypoint).

-- Extensions (require superuser)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Trigger function for updated_at auto-update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Default privileges: grant DML on future tables/sequences to the app user
-- (Alembic creates tables as the app user, so this covers new tables)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO current_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO current_user;

DO $$
BEGIN
    RAISE NOTICE 'UK Management init complete: extensions and default privileges configured.';
    RAISE NOTICE 'Schema is managed by Alembic — run "alembic upgrade head" to create tables.';
END $$;
