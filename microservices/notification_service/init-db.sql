-- Initialize Notification Service Database
-- UK Management Bot - Microservices

-- Create database if it doesn't exist (this will be handled by POSTGRES_DB)
-- CREATE DATABASE IF NOT EXISTS uk_notifications_db;

-- Grant privileges to the user (handled by POSTGRES_USER/POSTGRES_PASSWORD)
-- GRANT ALL PRIVILEGES ON DATABASE uk_notifications_db TO uk_notifications_user;

-- Set timezone
SET timezone = 'UTC';

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Note: SQLAlchemy will create the actual tables via alembic/create_all()
-- This file is mainly for database initialization and extensions