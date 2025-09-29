-- AI Service Database Initialization
-- UK Management Bot - Microservices

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Basic assignments table
CREATE TABLE IF NOT EXISTS ai_assignments (
    id SERIAL PRIMARY KEY,
    request_number VARCHAR(20) NOT NULL,
    executor_id INTEGER NOT NULL,
    algorithm_used VARCHAR(50) NOT NULL,
    assignment_score FLOAT NOT NULL DEFAULT 0.0,
    factors JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ML models metadata
CREATE TABLE IF NOT EXISTS ml_models (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    version VARCHAR(20) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    training_config JSONB NOT NULL DEFAULT '{}',
    training_data_hash VARCHAR(64),
    training_samples INTEGER DEFAULT 0,
    training_duration_seconds INTEGER DEFAULT 0,
    validation_accuracy FLOAT,
    validation_precision FLOAT,
    validation_recall FLOAT,
    validation_f1_score FLOAT,
    is_active BOOLEAN DEFAULT false,
    trained_at TIMESTAMP WITH TIME ZONE NOT NULL,
    activated_at TIMESTAMP WITH TIME ZONE,
    deactivated_at TIMESTAMP WITH TIME ZONE,
    model_path TEXT NOT NULL,
    feature_schema JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique constraint for active models
CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_models_active_type
ON ml_models(model_type) WHERE is_active = true;

-- Model predictions tracking
CREATE TABLE IF NOT EXISTS model_predictions (
    id SERIAL PRIMARY KEY,
    model_id VARCHAR(100) REFERENCES ml_models(id),
    prediction_type VARCHAR(50) NOT NULL,
    input_features JSONB NOT NULL DEFAULT '{}',
    predicted_value FLOAT NOT NULL,
    confidence_score FLOAT,
    actual_value FLOAT,
    outcome_recorded_at TIMESTAMP WITH TIME ZONE,
    request_number VARCHAR(20),
    executor_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Model performance tracking
CREATE TABLE IF NOT EXISTS model_evaluations (
    id SERIAL PRIMARY KEY,
    model_id VARCHAR(100) REFERENCES ml_models(id),
    evaluation_date DATE NOT NULL,
    accuracy FLOAT NOT NULL,
    precision_score FLOAT,
    recall_score FLOAT,
    f1_score FLOAT,
    mae FLOAT,
    sample_count INTEGER NOT NULL,
    evaluation_period_days INTEGER NOT NULL,
    evaluation_config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique constraint for model evaluations per date
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_evaluations_model_date
ON model_evaluations(model_id, evaluation_date);

-- District mapping for geography
CREATE TABLE IF NOT EXISTS district_mapping (
    id SERIAL PRIMARY KEY,
    address_pattern TEXT NOT NULL,
    district VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    proximity_group INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert initial district data
INSERT INTO district_mapping (address_pattern, district, region, proximity_group) VALUES
    ('чиланзар', 'Чиланзар', 'West', 1),
    ('юнусабад', 'Юнусабад', 'North', 2),
    ('мирзо-улугбек', 'Мирзо-Улугбек', 'Center', 3),
    ('яшнабад', 'Яшнабад', 'South', 4),
    ('сергели', 'Сергели', 'East', 5)
ON CONFLICT DO NOTHING;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_ai_assignments_request_number ON ai_assignments(request_number);
CREATE INDEX IF NOT EXISTS idx_ai_assignments_executor_id ON ai_assignments(executor_id);
CREATE INDEX IF NOT EXISTS idx_ai_assignments_created_at ON ai_assignments(created_at);

CREATE INDEX IF NOT EXISTS idx_model_predictions_model_id ON model_predictions(model_id);
CREATE INDEX IF NOT EXISTS idx_model_predictions_request_number ON model_predictions(request_number);
CREATE INDEX IF NOT EXISTS idx_model_predictions_created_at ON model_predictions(created_at);

CREATE INDEX IF NOT EXISTS idx_district_mapping_pattern ON district_mapping(address_pattern);
CREATE INDEX IF NOT EXISTS idx_district_mapping_district ON district_mapping(district);

-- Update timestamps trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_ai_assignments_updated_at
    BEFORE UPDATE ON ai_assignments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ai_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ai_user;