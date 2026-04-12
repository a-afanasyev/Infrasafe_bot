#!/bin/bash
# UK Management Bot — PostgreSQL Init (bash companion to init_postgres.sql)
# Runs after the SQL init script in /docker-entrypoint-initdb.d/
#
# The postgres:15-alpine image already creates:
#   - Database: $POSTGRES_DB  (from env)
#   - User: $POSTGRES_USER with $POSTGRES_PASSWORD (from env)
# This script only verifies and grants permissions.

set -e

echo "Starting PostgreSQL post-init verification..."

until pg_isready -U "$POSTGRES_USER" -h localhost; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done

echo "PostgreSQL is ready."

# Grant permissions to the app user on the target database
psql -U postgres -d "$POSTGRES_DB" <<EOF
-- Grant connect and schema usage
GRANT CONNECT ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;
GRANT USAGE ON SCHEMA public TO $POSTGRES_USER;
GRANT CREATE ON SCHEMA public TO $POSTGRES_USER;

-- Grant DML on existing tables/sequences (if any from SQL init)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $POSTGRES_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $POSTGRES_USER;

-- Default privileges for tables created later by Alembic
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $POSTGRES_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO $POSTGRES_USER;
EOF

echo "Permissions configured for user: $POSTGRES_USER"

# Verify connection as app user
if psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "Connection test passed."
else
    echo "ERROR: Connection test failed for user $POSTGRES_USER"
    exit 1
fi

echo "PostgreSQL init complete."
