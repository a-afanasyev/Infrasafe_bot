-- Request Service Database Initialization
-- UK Management Bot - Request Management System

-- Create database extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schema for request service
CREATE SCHEMA IF NOT EXISTS request_service;

-- Set default search path
SET search_path TO request_service, public;

-- Grant permissions to the request user
GRANT ALL PRIVILEGES ON SCHEMA request_service TO request_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA request_service TO request_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA request_service TO request_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA request_service GRANT ALL ON TABLES TO request_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA request_service GRANT ALL ON SEQUENCES TO request_user;