-- Analytics Service - Building Dimension Table Migration
-- Task 10.1 - Create dim_buildings with SCD Type 2
--
-- Purpose: Dimension table for Building Directory integration
-- SCD Type 2: Track historical changes to building data
--
-- Run: psql -U analytics_user -d analytics_db -f 001_create_dim_buildings.sql

-- ============================================================================
-- Create dim_buildings table
-- ============================================================================

CREATE TABLE IF NOT EXISTS dim_buildings (
    -- Surrogate key
    building_key SERIAL PRIMARY KEY,

    -- Natural key (from Building Directory)
    building_id UUID NOT NULL,

    -- SCD Type 2 fields
    effective_from TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMP NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    -- Management company (tenant isolation)
    management_company_id UUID NOT NULL,

    -- Address components
    city VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    street VARCHAR(200) NOT NULL,
    house_number VARCHAR(20) NOT NULL,
    building_corpus VARCHAR(20),
    full_address VARCHAR(500) NOT NULL,

    -- Geographic coordinates
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    coordinates_source VARCHAR(50),

    -- Building metadata
    building_type VARCHAR(50),
    floors_count INTEGER,
    apartments_count INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Audit fields
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes for SCD Type 2 queries
-- ============================================================================

-- Fast lookup of current version by natural key
CREATE INDEX ix_dim_buildings_building_id ON dim_buildings(building_id);
CREATE UNIQUE INDEX ix_dim_buildings_natural_key_current
    ON dim_buildings(building_id)
    WHERE is_current = true;

-- SCD Type 2 temporal queries
CREATE INDEX ix_dim_buildings_effective_from ON dim_buildings(effective_from);
CREATE INDEX ix_dim_buildings_effective_to ON dim_buildings(effective_to);
CREATE INDEX ix_dim_buildings_is_current ON dim_buildings(is_current);
CREATE INDEX ix_dim_buildings_effective_range
    ON dim_buildings(building_id, effective_from, effective_to);

-- ============================================================================
-- Analytics indexes
-- ============================================================================

-- City-based analytics
CREATE INDEX ix_dim_buildings_city ON dim_buildings(city);
CREATE INDEX ix_dim_buildings_city_active
    ON dim_buildings(city, is_active, is_current);

-- Company-level analytics (tenant isolation)
CREATE INDEX ix_dim_buildings_company ON dim_buildings(management_company_id);
CREATE INDEX ix_dim_buildings_company_active
    ON dim_buildings(management_company_id, is_active, is_current);

-- Spatial queries (partial index for performance)
CREATE INDEX ix_dim_buildings_coordinates
    ON dim_buildings(latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Status queries
CREATE INDEX ix_dim_buildings_active ON dim_buildings(is_active);

-- Full address search
CREATE INDEX ix_dim_buildings_full_address ON dim_buildings(full_address);

-- ============================================================================
-- Triggers for automatic updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_dim_buildings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dim_buildings_updated_at
    BEFORE UPDATE ON dim_buildings
    FOR EACH ROW
    EXECUTE FUNCTION update_dim_buildings_updated_at();

-- ============================================================================
-- Helper functions for SCD Type 2 operations
-- ============================================================================

-- Function to expire current version and insert new version
CREATE OR REPLACE FUNCTION upsert_dim_building(
    p_building_id UUID,
    p_management_company_id UUID,
    p_city VARCHAR(100),
    p_district VARCHAR(100),
    p_street VARCHAR(200),
    p_house_number VARCHAR(20),
    p_building_corpus VARCHAR(20),
    p_full_address VARCHAR(500),
    p_latitude NUMERIC(10, 8),
    p_longitude NUMERIC(11, 8),
    p_coordinates_source VARCHAR(50),
    p_building_type VARCHAR(50),
    p_floors_count INTEGER,
    p_apartments_count INTEGER,
    p_is_active BOOLEAN
)
RETURNS INTEGER AS $$
DECLARE
    v_building_key INTEGER;
    v_current_record RECORD;
    v_has_changes BOOLEAN := FALSE;
BEGIN
    -- Get current version if exists
    SELECT * INTO v_current_record
    FROM dim_buildings
    WHERE building_id = p_building_id AND is_current = TRUE;

    -- If no current record exists, insert new
    IF NOT FOUND THEN
        INSERT INTO dim_buildings (
            building_id, management_company_id,
            city, district, street, house_number, building_corpus, full_address,
            latitude, longitude, coordinates_source,
            building_type, floors_count, apartments_count, is_active,
            effective_from, effective_to, is_current
        ) VALUES (
            p_building_id, p_management_company_id,
            p_city, p_district, p_street, p_house_number, p_building_corpus, p_full_address,
            p_latitude, p_longitude, p_coordinates_source,
            p_building_type, p_floors_count, p_apartments_count, p_is_active,
            NOW(), NULL, TRUE
        )
        RETURNING building_key INTO v_building_key;

        RETURN v_building_key;
    END IF;

    -- Check if any tracked fields have changed
    v_has_changes := (
        COALESCE(v_current_record.city, '') != COALESCE(p_city, '') OR
        COALESCE(v_current_record.district, '') != COALESCE(p_district, '') OR
        COALESCE(v_current_record.street, '') != COALESCE(p_street, '') OR
        COALESCE(v_current_record.house_number, '') != COALESCE(p_house_number, '') OR
        COALESCE(v_current_record.building_corpus, '') != COALESCE(p_building_corpus, '') OR
        COALESCE(v_current_record.full_address, '') != COALESCE(p_full_address, '') OR
        COALESCE(v_current_record.latitude, 0) != COALESCE(p_latitude, 0) OR
        COALESCE(v_current_record.longitude, 0) != COALESCE(p_longitude, 0) OR
        COALESCE(v_current_record.is_active, FALSE) != COALESCE(p_is_active, FALSE)
    );

    -- If no changes, just update metadata and return existing key
    IF NOT v_has_changes THEN
        UPDATE dim_buildings
        SET
            building_type = p_building_type,
            floors_count = p_floors_count,
            apartments_count = p_apartments_count,
            coordinates_source = p_coordinates_source,
            updated_at = NOW()
        WHERE building_key = v_current_record.building_key;

        RETURN v_current_record.building_key;
    END IF;

    -- Changes detected - expire current version
    UPDATE dim_buildings
    SET
        effective_to = NOW(),
        is_current = FALSE,
        updated_at = NOW()
    WHERE building_key = v_current_record.building_key;

    -- Insert new version
    INSERT INTO dim_buildings (
        building_id, management_company_id,
        city, district, street, house_number, building_corpus, full_address,
        latitude, longitude, coordinates_source,
        building_type, floors_count, apartments_count, is_active,
        effective_from, effective_to, is_current
    ) VALUES (
        p_building_id, p_management_company_id,
        p_city, p_district, p_street, p_house_number, p_building_corpus, p_full_address,
        p_latitude, p_longitude, p_coordinates_source,
        p_building_type, p_floors_count, p_apartments_count, p_is_active,
        NOW(), NULL, TRUE
    )
    RETURNING building_key INTO v_building_key;

    RETURN v_building_key;
END;
$$ LANGUAGE plpgsql;

-- Function to get current version of building
CREATE OR REPLACE FUNCTION get_current_dim_building(p_building_id UUID)
RETURNS TABLE (
    building_key INTEGER,
    building_id UUID,
    full_address VARCHAR(500),
    city VARCHAR(100),
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    is_active BOOLEAN,
    effective_from TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        db.building_key,
        db.building_id,
        db.full_address,
        db.city,
        db.latitude,
        db.longitude,
        db.is_active,
        db.effective_from
    FROM dim_buildings db
    WHERE db.building_id = p_building_id AND db.is_current = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to get building version at specific time
CREATE OR REPLACE FUNCTION get_dim_building_at_time(
    p_building_id UUID,
    p_timestamp TIMESTAMP
)
RETURNS TABLE (
    building_key INTEGER,
    building_id UUID,
    full_address VARCHAR(500),
    city VARCHAR(100),
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    is_active BOOLEAN,
    effective_from TIMESTAMP,
    effective_to TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        db.building_key,
        db.building_id,
        db.full_address,
        db.city,
        db.latitude,
        db.longitude,
        db.is_active,
        db.effective_from,
        db.effective_to
    FROM dim_buildings db
    WHERE
        db.building_id = p_building_id
        AND db.effective_from <= p_timestamp
        AND (db.effective_to IS NULL OR db.effective_to > p_timestamp);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Table comments
-- ============================================================================

COMMENT ON TABLE dim_buildings IS 'Building dimension table with SCD Type 2 for historical tracking';
COMMENT ON COLUMN dim_buildings.building_key IS 'Surrogate key for dimension table';
COMMENT ON COLUMN dim_buildings.building_id IS 'Natural key - UUID from Building Directory';
COMMENT ON COLUMN dim_buildings.effective_from IS 'When this version became effective';
COMMENT ON COLUMN dim_buildings.effective_to IS 'When this version was superseded (NULL = current)';
COMMENT ON COLUMN dim_buildings.is_current IS 'Flag indicating current version';

-- ============================================================================
-- Sample queries for verification
-- ============================================================================

-- Get current version of all buildings
-- SELECT * FROM dim_buildings WHERE is_current = TRUE;

-- Get building history
-- SELECT * FROM dim_buildings WHERE building_id = 'your-uuid-here' ORDER BY effective_from;

-- Get building version at specific time
-- SELECT * FROM get_dim_building_at_time('your-uuid-here', '2024-06-01'::TIMESTAMP);

-- Count buildings by city (current only)
-- SELECT city, COUNT(*) FROM dim_buildings WHERE is_current = TRUE GROUP BY city;

-- ============================================================================
-- Migration complete
-- ============================================================================

-- Verify table creation
SELECT
    'dim_buildings table created' AS status,
    COUNT(*) AS index_count
FROM pg_indexes
WHERE tablename = 'dim_buildings';
