-- Shift Service Database Initialization Script
-- UK Management Bot - Shift Service

-- Create shift database user and grant permissions
CREATE USER shift_user WITH PASSWORD 'shift_pass';

-- Create shift_db database if it doesn't exist
SELECT 'CREATE DATABASE shift_db' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'shift_db')\gexec

-- Grant all privileges on shift_db to shift_user
GRANT ALL PRIVILEGES ON DATABASE shift_db TO shift_user;

-- Connect to shift_db
\c shift_db

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO shift_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO shift_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO shift_user;

-- Ensure future tables and sequences have correct permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO shift_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO shift_user;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create timezone support
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Optimize for shift operations
SET timezone = 'UTC';

-- Performance optimizations for shift scheduling
SET shared_preload_libraries = 'pg_stat_statements';
SET track_activities = on;
SET track_counts = on;
SET track_io_timing = on;

-- Create indexes for common shift queries
-- Note: Actual indexes will be created by SQLAlchemy migrations