-- Integration Service Database Initialization
-- UK Management Bot - Integration Service
-- PostgreSQL Extensions and Setup

-- Create necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "btree_gist";  -- For better indexing

-- Create integration schema
CREATE SCHEMA IF NOT EXISTS integration;

-- Set search path
SET search_path TO integration, public;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA integration TO integration_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA integration TO integration_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA integration TO integration_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA integration TO integration_user;

-- Enable row-level security
ALTER DATABASE integration_db SET row_security = on;

-- Create audit triggers function
CREATE OR REPLACE FUNCTION integration.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE '✅ Integration Service database initialized successfully';
    RAISE NOTICE '📊 Extensions: uuid-ossp, pg_trgm, btree_gist';
    RAISE NOTICE '🔐 Schema: integration created with proper permissions';
END $$;
