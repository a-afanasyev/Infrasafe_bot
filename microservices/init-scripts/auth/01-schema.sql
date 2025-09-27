-- Auth Service Database Schema
-- UK Management Bot - Sprint 0

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create schema
CREATE SCHEMA IF NOT EXISTS auth;
SET search_path TO auth, public;

-- JWT tokens table
CREATE TABLE IF NOT EXISTS jwt_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL,
    token_hash VARCHAR(256) NOT NULL UNIQUE,
    token_type VARCHAR(20) NOT NULL CHECK (token_type IN ('access', 'refresh')),
    issued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    device_info JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_jwt_tokens_user_id (user_id),
    INDEX idx_jwt_tokens_token_hash (token_hash),
    INDEX idx_jwt_tokens_expires_at (expires_at),
    INDEX idx_jwt_tokens_revoked (revoked)
);

-- Session storage
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(256) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    data JSONB,
    ip_address INET,
    user_agent TEXT,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sessions_user_id (user_id),
    INDEX idx_sessions_session_id (session_id),
    INDEX idx_sessions_expires_at (expires_at)
);

-- Password reset tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL,
    token_hash VARCHAR(256) NOT NULL UNIQUE,
    used BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP WITH TIME ZONE,
    ip_address INET,
    INDEX idx_password_reset_tokens_user_id (user_id),
    INDEX idx_password_reset_tokens_token_hash (token_hash),
    INDEX idx_password_reset_tokens_expires_at (expires_at)
);

-- Authentication attempts log
CREATE TABLE IF NOT EXISTS auth_attempts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    username VARCHAR(100),
    attempt_type VARCHAR(50) NOT NULL,
    success BOOLEAN NOT NULL,
    ip_address INET,
    user_agent TEXT,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_auth_attempts_user_id (user_id),
    INDEX idx_auth_attempts_ip_address (ip_address),
    INDEX idx_auth_attempts_created_at (created_at DESC)
);

-- Account lockout tracking
CREATE TABLE IF NOT EXISTS account_lockouts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    locked_until TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT,
    attempt_count INTEGER DEFAULT 0,
    unlocked_at TIMESTAMP WITH TIME ZONE,
    unlocked_by BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_account_lockouts_user_id (user_id),
    INDEX idx_account_lockouts_locked_until (locked_until)
);

-- API keys for service-to-service communication
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(256) NOT NULL UNIQUE,
    permissions JSONB,
    rate_limit INTEGER DEFAULT 1000,
    active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_api_keys_key_hash (key_hash),
    INDEX idx_api_keys_service_name (service_name),
    INDEX idx_api_keys_active (active)
);

-- Audit log for auth events
CREATE TABLE IF NOT EXISTS auth_audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    user_id BIGINT,
    service_name VARCHAR(100),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_auth_audit_log_user_id (user_id),
    INDEX idx_auth_audit_log_event_type (event_type),
    INDEX idx_auth_audit_log_created_at (created_at DESC)
);

-- Create function for updating updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for api_keys
CREATE TRIGGER update_api_keys_updated_at
    BEFORE UPDATE ON api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create cleanup function for expired tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void AS $$
BEGIN
    -- Delete expired JWT tokens older than 30 days
    DELETE FROM jwt_tokens
    WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

    -- Delete expired sessions
    DELETE FROM sessions
    WHERE expires_at < CURRENT_TIMESTAMP;

    -- Delete used or expired password reset tokens older than 7 days
    DELETE FROM password_reset_tokens
    WHERE (used = TRUE OR expires_at < CURRENT_TIMESTAMP)
    AND created_at < CURRENT_TIMESTAMP - INTERVAL '7 days';

    -- Clean old auth attempts (keep last 90 days)
    DELETE FROM auth_attempts
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '90 days';

    -- Clean old audit logs (keep last 1 year)
    DELETE FROM auth_audit_log
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 year';
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA auth TO uk_auth_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA auth TO uk_auth_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA auth TO uk_auth_user;