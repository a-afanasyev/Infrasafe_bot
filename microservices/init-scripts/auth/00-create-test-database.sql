-- Create test database for Auth Service
-- This script runs before 01-schema.sql to ensure test database exists

-- Create test database
CREATE DATABASE auth_db_test;

-- Grant permissions to auth_user
GRANT ALL PRIVILEGES ON DATABASE auth_db_test TO auth_user;
