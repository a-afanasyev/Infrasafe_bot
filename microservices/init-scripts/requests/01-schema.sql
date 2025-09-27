-- Requests Service Database Schema
-- UK Management Bot - Sprint 0
-- CRITICAL: Uses request_number (YYMMDD-NNN) as primary identifier

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create schema
CREATE SCHEMA IF NOT EXISTS requests;
SET search_path TO requests, public;

-- Request number sequence table (for daily counter)
CREATE TABLE IF NOT EXISTS request_number_sequences (
    date DATE PRIMARY KEY,
    last_sequence INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Requests table (migrated from monolith with new numbering system)
CREATE TABLE IF NOT EXISTS requests (
    request_number VARCHAR(12) PRIMARY KEY, -- Format: YYMMDD-NNN
    user_id BIGINT NOT NULL,
    assigned_to BIGINT,
    request_type VARCHAR(50) NOT NULL,
    specialization VARCHAR(50),
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    title TEXT NOT NULL,
    description TEXT,
    address JSONB,
    contact_phone VARCHAR(20),
    preferred_date DATE,
    preferred_time TIME,
    actual_start_time TIMESTAMP WITH TIME ZONE,
    actual_end_time TIMESTAMP WITH TIME ZONE,
    estimated_duration INTEGER, -- in minutes
    actual_duration INTEGER, -- in minutes
    media_files JSONB DEFAULT '[]',
    completion_media JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    notes TEXT,
    internal_notes TEXT,
    rejection_reason TEXT,
    cancellation_reason TEXT,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    rating_comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT check_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    CONSTRAINT check_status CHECK (status IN (
        'pending', 'assigned', 'in_progress', 'completed',
        'cancelled', 'rejected', 'on_hold', 'awaiting_payment'
    )),
    INDEX idx_requests_user_id (user_id),
    INDEX idx_requests_assigned_to (assigned_to),
    INDEX idx_requests_status (status),
    INDEX idx_requests_priority (priority),
    INDEX idx_requests_request_type (request_type),
    INDEX idx_requests_created_at (created_at DESC),
    INDEX idx_requests_preferred_date (preferred_date)
);

-- Request status history
CREATE TABLE IF NOT EXISTS request_status_history (
    id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(12) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,
    old_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    changed_by BIGINT,
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_request_status_history_request_number (request_number),
    INDEX idx_request_status_history_created_at (created_at DESC)
);

-- Request comments
CREATE TABLE IF NOT EXISTS request_comments (
    id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(12) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    comment_type VARCHAR(50) DEFAULT 'general',
    content TEXT NOT NULL,
    is_internal BOOLEAN DEFAULT FALSE,
    media_files JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_request_comments_request_number (request_number),
    INDEX idx_request_comments_user_id (user_id),
    INDEX idx_request_comments_created_at (created_at DESC),
    INDEX idx_request_comments_is_internal (is_internal)
);

-- Request assignments history
CREATE TABLE IF NOT EXISTS request_assignment_history (
    id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(12) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,
    assigned_to BIGINT,
    assigned_by BIGINT,
    assignment_type VARCHAR(50) DEFAULT 'manual',
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_request_assignment_history_request_number (request_number),
    INDEX idx_request_assignment_history_assigned_to (assigned_to),
    INDEX idx_request_assignment_history_created_at (created_at DESC)
);

-- Request materials (for tracking costs)
CREATE TABLE IF NOT EXISTS request_materials (
    id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(12) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,
    material_name VARCHAR(255) NOT NULL,
    quantity DECIMAL(10, 2),
    unit VARCHAR(50),
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2),
    purchased_by BIGINT,
    purchased_at TIMESTAMP WITH TIME ZONE,
    receipt_url TEXT,
    approved_by BIGINT,
    approved_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_request_materials_request_number (request_number),
    INDEX idx_request_materials_purchased_by (purchased_by)
);

-- Request SLA tracking
CREATE TABLE IF NOT EXISTS request_sla_tracking (
    id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(12) NOT NULL UNIQUE REFERENCES requests(request_number) ON DELETE CASCADE,
    sla_type VARCHAR(50) NOT NULL,
    target_response_time INTEGER, -- in minutes
    target_completion_time INTEGER, -- in minutes
    actual_response_time INTEGER, -- in minutes
    actual_completion_time INTEGER, -- in minutes
    sla_met BOOLEAN,
    breach_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_request_sla_tracking_request_number (request_number),
    INDEX idx_request_sla_tracking_sla_met (sla_met)
);

-- Request templates (for recurring requests)
CREATE TABLE IF NOT EXISTS request_templates (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    user_id BIGINT NOT NULL,
    request_type VARCHAR(50) NOT NULL,
    specialization VARCHAR(50),
    priority VARCHAR(20) DEFAULT 'normal',
    title TEXT NOT NULL,
    description TEXT,
    address JSONB,
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_request_templates_user_id (user_id),
    INDEX idx_request_templates_is_active (is_active)
);

-- Function to generate request number
CREATE OR REPLACE FUNCTION generate_request_number()
RETURNS VARCHAR AS $$
DECLARE
    current_date DATE := CURRENT_DATE;
    date_string VARCHAR(6);
    next_sequence INTEGER;
    new_request_number VARCHAR(12);
BEGIN
    -- Format date as YYMMDD
    date_string := TO_CHAR(current_date, 'YYMMDD');

    -- Get next sequence number for today
    INSERT INTO request_number_sequences (date, last_sequence)
    VALUES (current_date, 1)
    ON CONFLICT (date) DO UPDATE
    SET last_sequence = request_number_sequences.last_sequence + 1,
        updated_at = CURRENT_TIMESTAMP
    RETURNING last_sequence INTO next_sequence;

    -- Generate request number
    new_request_number := date_string || '-' || LPAD(next_sequence::TEXT, 3, '0');

    RETURN new_request_number;
END;
$$ LANGUAGE plpgsql;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers
CREATE TRIGGER update_requests_updated_at BEFORE UPDATE ON requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_request_comments_updated_at BEFORE UPDATE ON request_comments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_request_materials_updated_at BEFORE UPDATE ON request_materials
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_request_sla_tracking_updated_at BEFORE UPDATE ON request_sla_tracking
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_request_templates_updated_at BEFORE UPDATE ON request_templates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_request_number_sequences_updated_at BEFORE UPDATE ON request_number_sequences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA requests TO uk_requests_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA requests TO uk_requests_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA requests TO uk_requests_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA requests TO uk_requests_user;