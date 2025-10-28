-- ======================================================================
-- UK Management Bot - PostgreSQL Database Schema (ACTUAL)
-- Generated from SQLAlchemy models
-- Date: 2025-10-15
-- ======================================================================

-- ======================================================================
-- ENUM Types
-- ======================================================================

-- AccessLevel enum for access_rights table
CREATE TYPE accesslevel AS ENUM ('apartment', 'house', 'yard');

-- DocumentType enum for user_documents table
CREATE TYPE documenttype AS ENUM ('passport', 'property_deed', 'rental_agreement', 'utility_bill', 'other');

-- VerificationStatus enum for user_documents and user_verifications tables
CREATE TYPE verificationstatus AS ENUM ('pending', 'approved', 'rejected', 'requested');

-- ======================================================================
-- Tables
-- ======================================================================

-- Table: shift_templates
----------------------------------------------------------------------
CREATE TABLE shift_templates (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	start_hour INTEGER NOT NULL, 
	start_minute INTEGER NOT NULL, 
	duration_hours INTEGER NOT NULL, 
	required_specializations JSON, 
	min_executors INTEGER NOT NULL, 
	max_executors INTEGER NOT NULL, 
	default_max_requests INTEGER NOT NULL, 
	coverage_areas JSON, 
	geographic_zone VARCHAR(100), 
	priority_level INTEGER NOT NULL, 
	auto_create BOOLEAN NOT NULL, 
	days_of_week JSON, 
	advance_days INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	default_shift_type VARCHAR(50) NOT NULL, 
	settings JSON, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_shift_templates_id ON shift_templates (id);


-- Table: users
----------------------------------------------------------------------
CREATE TABLE users (
	id SERIAL NOT NULL, 
	telegram_id BIGINT NOT NULL, 
	username VARCHAR(255), 
	first_name VARCHAR(255), 
	last_name VARCHAR(255), 
	role VARCHAR(50) NOT NULL, 
	roles TEXT, 
	active_role VARCHAR(50), 
	status VARCHAR(50) NOT NULL, 
	language VARCHAR(10) NOT NULL, 
	phone VARCHAR(20), 
	specialization TEXT, 
	verification_status VARCHAR(50) NOT NULL, 
	verification_notes TEXT, 
	verification_date TIMESTAMP WITH TIME ZONE, 
	verified_by INTEGER, 
	passport_series VARCHAR(10), 
	passport_number VARCHAR(10), 
	birth_date TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_telegram_id ON users (telegram_id);


-- Table: access_rights
----------------------------------------------------------------------
CREATE TABLE access_rights (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	access_level accesslevel NOT NULL, 
	apartment_number VARCHAR(20), 
	house_number VARCHAR(20), 
	yard_name VARCHAR(100), 
	is_active BOOLEAN, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	granted_by INTEGER NOT NULL, 
	granted_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(granted_by) REFERENCES users (id)
);

CREATE INDEX ix_access_rights_id ON access_rights (id);


-- Table: audit_logs
----------------------------------------------------------------------
CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	telegram_user_id INTEGER, 
	action VARCHAR(100) NOT NULL, 
	details JSON, 
	ip_address VARCHAR(45), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_logs_telegram_user_id ON audit_logs (telegram_user_id);
CREATE INDEX ix_audit_logs_id ON audit_logs (id);


-- Table: notifications
----------------------------------------------------------------------
CREATE TABLE notifications (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	notification_type VARCHAR(50) NOT NULL, 
	title VARCHAR(255), 
	content TEXT NOT NULL, 
	is_read BOOLEAN, 
	is_sent BOOLEAN, 
	meta_data JSON, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_notifications_id ON notifications (id);


-- Table: quarterly_plans
----------------------------------------------------------------------
CREATE TABLE quarterly_plans (
	id SERIAL NOT NULL, 
	year INTEGER NOT NULL, 
	quarter INTEGER NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	created_by INTEGER NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	specializations JSON, 
	coverage_24_7 BOOLEAN NOT NULL, 
	load_balancing_enabled BOOLEAN NOT NULL, 
	auto_transfers_enabled BOOLEAN NOT NULL, 
	notifications_enabled BOOLEAN NOT NULL, 
	total_shifts_planned INTEGER NOT NULL, 
	total_hours_planned FLOAT NOT NULL, 
	coverage_percentage FLOAT NOT NULL, 
	total_conflicts INTEGER NOT NULL, 
	resolved_conflicts INTEGER NOT NULL, 
	pending_conflicts INTEGER NOT NULL, 
	settings JSON, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_quarterly_plans_id ON quarterly_plans (id);


-- Table: shift_schedules
----------------------------------------------------------------------
CREATE TABLE shift_schedules (
	id SERIAL NOT NULL, 
	date DATE NOT NULL, 
	planned_coverage JSON, 
	actual_coverage JSON, 
	planned_specialization_coverage JSON, 
	actual_specialization_coverage JSON, 
	predicted_requests INTEGER, 
	actual_requests INTEGER NOT NULL, 
	prediction_accuracy FLOAT, 
	recommended_shifts INTEGER, 
	actual_shifts INTEGER NOT NULL, 
	optimization_score FLOAT, 
	coverage_percentage FLOAT, 
	load_balance_score FLOAT, 
	special_conditions JSON, 
	manual_adjustments JSON, 
	notes VARCHAR(500), 
	status VARCHAR(50) NOT NULL, 
	created_by INTEGER, 
	auto_generated BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_shift_schedules_date ON shift_schedules (date);
CREATE INDEX ix_shift_schedules_id ON shift_schedules (id);


-- Table: shifts
----------------------------------------------------------------------
CREATE TABLE shifts (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	end_time TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(50) NOT NULL, 
	notes TEXT, 
	planned_start_time TIMESTAMP WITH TIME ZONE, 
	planned_end_time TIMESTAMP WITH TIME ZONE, 
	shift_template_id INTEGER, 
	shift_type VARCHAR(50), 
	specialization_focus JSON, 
	coverage_areas JSON, 
	geographic_zone VARCHAR(100), 
	max_requests INTEGER NOT NULL, 
	current_request_count INTEGER NOT NULL, 
	priority_level INTEGER NOT NULL, 
	completed_requests INTEGER NOT NULL, 
	average_completion_time FLOAT, 
	average_response_time FLOAT, 
	efficiency_score FLOAT, 
	quality_rating FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(shift_template_id) REFERENCES shift_templates (id)
);

CREATE INDEX ix_shifts_id ON shifts (id);


-- Table: user_documents
----------------------------------------------------------------------
CREATE TABLE user_documents (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	document_type documenttype NOT NULL, 
	file_id VARCHAR(255) NOT NULL, 
	file_name VARCHAR(255), 
	file_size INTEGER, 
	verification_status verificationstatus, 
	verification_notes TEXT, 
	verified_by INTEGER, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(verified_by) REFERENCES users (id)
);

CREATE INDEX ix_user_documents_id ON user_documents (id);


-- Table: user_verifications
----------------------------------------------------------------------
CREATE TABLE user_verifications (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	status verificationstatus, 
	requested_info JSON, 
	requested_at TIMESTAMP WITH TIME ZONE, 
	requested_by INTEGER, 
	admin_notes TEXT, 
	verified_by INTEGER, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id), 
	FOREIGN KEY(verified_by) REFERENCES users (id)
);

CREATE INDEX ix_user_verifications_id ON user_verifications (id);


-- Table: yards
----------------------------------------------------------------------
CREATE TABLE yards (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	gps_latitude FLOAT, 
	gps_longitude FLOAT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	created_by INTEGER, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_yards_name ON yards (name);
CREATE INDEX ix_yards_id ON yards (id);
CREATE INDEX ix_yards_is_active ON yards (is_active);


-- Table: buildings
----------------------------------------------------------------------
CREATE TABLE buildings (
	id SERIAL NOT NULL, 
	address VARCHAR(300) NOT NULL, 
	yard_id INTEGER NOT NULL, 
	gps_latitude FLOAT, 
	gps_longitude FLOAT, 
	entrance_count INTEGER NOT NULL, 
	floor_count INTEGER NOT NULL, 
	description TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	created_by INTEGER, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(yard_id) REFERENCES yards (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_buildings_is_active ON buildings (is_active);
CREATE INDEX ix_buildings_id ON buildings (id);
CREATE INDEX ix_buildings_address ON buildings (address);
CREATE INDEX ix_buildings_yard_id ON buildings (yard_id);


-- Table: planning_conflicts
----------------------------------------------------------------------
CREATE TABLE planning_conflicts (
	id SERIAL NOT NULL, 
	quarterly_plan_id INTEGER NOT NULL, 
	conflict_type VARCHAR(100) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	involved_schedule_ids JSON, 
	involved_user_ids JSON, 
	conflict_time TIMESTAMP WITH TIME ZONE, 
	conflict_date DATE, 
	conflict_details JSON, 
	description TEXT, 
	suggested_resolutions JSON, 
	applied_resolution JSON, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	resolved_by INTEGER, 
	priority INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(quarterly_plan_id) REFERENCES quarterly_plans (id), 
	FOREIGN KEY(resolved_by) REFERENCES users (id)
);

CREATE INDEX ix_planning_conflicts_id ON planning_conflicts (id);


-- Table: quarterly_shift_schedules
----------------------------------------------------------------------
CREATE TABLE quarterly_shift_schedules (
	id SERIAL NOT NULL, 
	quarterly_plan_id INTEGER NOT NULL, 
	planned_date DATE NOT NULL, 
	planned_start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	planned_end_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	assigned_user_id INTEGER, 
	specialization VARCHAR(100) NOT NULL, 
	schedule_type VARCHAR(50) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	actual_shift_id INTEGER, 
	shift_config JSON, 
	coverage_areas JSON, 
	priority INTEGER NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(quarterly_plan_id) REFERENCES quarterly_plans (id), 
	FOREIGN KEY(assigned_user_id) REFERENCES users (id), 
	FOREIGN KEY(actual_shift_id) REFERENCES shifts (id)
);

CREATE INDEX ix_quarterly_shift_schedules_id ON quarterly_shift_schedules (id);


-- Table: shift_transfers
----------------------------------------------------------------------
CREATE TABLE shift_transfers (
	id SERIAL NOT NULL, 
	shift_id INTEGER NOT NULL, 
	from_executor_id INTEGER NOT NULL, 
	to_executor_id INTEGER, 
	status VARCHAR(50) NOT NULL, 
	reason VARCHAR(100) NOT NULL, 
	comment TEXT, 
	urgency_level VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	assigned_at TIMESTAMP WITHOUT TIME ZONE, 
	responded_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	auto_assigned BOOLEAN NOT NULL, 
	retry_count INTEGER NOT NULL, 
	max_retries INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(shift_id) REFERENCES shifts (id), 
	FOREIGN KEY(from_executor_id) REFERENCES users (id), 
	FOREIGN KEY(to_executor_id) REFERENCES users (id)
);

CREATE INDEX ix_shift_transfers_to_executor_id ON shift_transfers (to_executor_id);
CREATE INDEX ix_shift_transfers_shift_id ON shift_transfers (shift_id);
CREATE INDEX ix_shift_transfers_created_at ON shift_transfers (created_at);
CREATE INDEX ix_shift_transfers_status ON shift_transfers (status);
CREATE INDEX ix_shift_transfers_from_executor_id ON shift_transfers (from_executor_id);
CREATE INDEX ix_shift_transfers_id ON shift_transfers (id);
CREATE INDEX ix_shift_transfers_reason ON shift_transfers (reason);
CREATE INDEX ix_shift_transfers_assigned_at ON shift_transfers (assigned_at);


-- Table: user_yards
----------------------------------------------------------------------
CREATE TABLE user_yards (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	yard_id INTEGER NOT NULL, 
	granted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	granted_by INTEGER, 
	comment TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_user_yard UNIQUE (user_id, yard_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(yard_id) REFERENCES yards (id) ON DELETE CASCADE, 
	FOREIGN KEY(granted_by) REFERENCES users (id)
);

CREATE INDEX ix_user_yards_id ON user_yards (id);
CREATE INDEX ix_user_yards_user_id ON user_yards (user_id);
CREATE INDEX ix_user_yards_yard_id ON user_yards (yard_id);


-- Table: apartments
----------------------------------------------------------------------
CREATE TABLE apartments (
	id SERIAL NOT NULL, 
	building_id INTEGER NOT NULL, 
	apartment_number VARCHAR(20) NOT NULL, 
	entrance INTEGER, 
	floor INTEGER, 
	rooms_count INTEGER, 
	area FLOAT, 
	description TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	created_by INTEGER, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_building_apartment UNIQUE (building_id, apartment_number), 
	FOREIGN KEY(building_id) REFERENCES buildings (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_apartments_id ON apartments (id);
CREATE INDEX ix_apartments_apartment_number ON apartments (apartment_number);
CREATE INDEX ix_apartments_building_id ON apartments (building_id);
CREATE INDEX ix_apartments_is_active ON apartments (is_active);


-- Table: requests
----------------------------------------------------------------------
CREATE TABLE requests (
	request_number VARCHAR(10) NOT NULL, 
	user_id INTEGER NOT NULL, 
	category VARCHAR(100) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	address TEXT, 
	description TEXT NOT NULL, 
	apartment VARCHAR(20), 
	urgency VARCHAR(20) NOT NULL, 
	apartment_id INTEGER, 
	media_files JSON, 
	executor_id INTEGER, 
	notes TEXT, 
	completion_report TEXT, 
	completion_media JSON, 
	assignment_type VARCHAR(20), 
	assigned_group VARCHAR(100), 
	assigned_at TIMESTAMP WITH TIME ZONE, 
	assigned_by INTEGER, 
	purchase_materials TEXT, 
	requested_materials TEXT, 
	manager_materials_comment TEXT, 
	purchase_history TEXT, 
	is_returned BOOLEAN NOT NULL, 
	return_reason TEXT, 
	return_media JSON, 
	returned_at TIMESTAMP WITH TIME ZONE, 
	returned_by INTEGER, 
	manager_confirmed BOOLEAN NOT NULL, 
	manager_confirmed_by INTEGER, 
	manager_confirmed_at TIMESTAMP WITH TIME ZONE, 
	manager_confirmation_notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (request_number), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(apartment_id) REFERENCES apartments (id), 
	FOREIGN KEY(executor_id) REFERENCES users (id), 
	FOREIGN KEY(assigned_by) REFERENCES users (id), 
	FOREIGN KEY(returned_by) REFERENCES users (id), 
	FOREIGN KEY(manager_confirmed_by) REFERENCES users (id)
);

CREATE INDEX ix_requests_apartment_id ON requests (apartment_id);
CREATE INDEX ix_requests_request_number ON requests (request_number);


-- Table: user_apartments
----------------------------------------------------------------------
CREATE TABLE user_apartments (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	apartment_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	reviewed_by INTEGER, 
	admin_comment TEXT, 
	is_owner BOOLEAN NOT NULL, 
	is_primary BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_user_apartment UNIQUE (user_id, apartment_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(apartment_id) REFERENCES apartments (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_user_apartments_apartment_id ON user_apartments (apartment_id);
CREATE INDEX ix_user_apartments_user_id ON user_apartments (user_id);
CREATE INDEX ix_user_apartments_id ON user_apartments (id);
CREATE INDEX ix_user_apartments_status ON user_apartments (status);


-- Table: ratings
----------------------------------------------------------------------
CREATE TABLE ratings (
	id SERIAL NOT NULL, 
	request_number VARCHAR(10) NOT NULL, 
	user_id INTEGER NOT NULL, 
	rating INTEGER NOT NULL, 
	review TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_number) REFERENCES requests (request_number), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_ratings_id ON ratings (id);


-- Table: request_assignments
----------------------------------------------------------------------
CREATE TABLE request_assignments (
	id SERIAL NOT NULL, 
	request_number VARCHAR(10) NOT NULL, 
	assignment_type VARCHAR(20) NOT NULL, 
	group_specialization VARCHAR(100), 
	executor_id INTEGER, 
	status VARCHAR(20), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	created_by INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_number) REFERENCES requests (request_number), 
	FOREIGN KEY(executor_id) REFERENCES users (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_request_assignments_id ON request_assignments (id);


-- Table: request_comments
----------------------------------------------------------------------
CREATE TABLE request_comments (
	id SERIAL NOT NULL, 
	request_number VARCHAR(10) NOT NULL, 
	user_id INTEGER NOT NULL, 
	comment_text TEXT NOT NULL, 
	comment_type VARCHAR(50) NOT NULL, 
	previous_status VARCHAR(50), 
	new_status VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_number) REFERENCES requests (request_number), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_request_comments_id ON request_comments (id);


-- Table: shift_assignments
----------------------------------------------------------------------
CREATE TABLE shift_assignments (
	id SERIAL NOT NULL, 
	shift_id INTEGER NOT NULL, 
	request_number VARCHAR(10) NOT NULL, 
	assignment_priority INTEGER NOT NULL, 
	estimated_duration INTEGER, 
	assignment_order INTEGER, 
	ai_score FLOAT, 
	confidence_level FLOAT, 
	specialization_match_score FLOAT, 
	geographic_score FLOAT, 
	workload_score FLOAT, 
	status VARCHAR(50) NOT NULL, 
	auto_assigned BOOLEAN NOT NULL, 
	confirmed_by_executor BOOLEAN NOT NULL, 
	assigned_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	planned_start_at TIMESTAMP WITH TIME ZONE, 
	planned_completion_at TIMESTAMP WITH TIME ZONE, 
	assignment_reason VARCHAR(200), 
	notes TEXT, 
	executor_instructions TEXT, 
	actual_duration INTEGER, 
	execution_quality_rating FLOAT, 
	had_issues BOOLEAN NOT NULL, 
	issues_description TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(shift_id) REFERENCES shifts (id) ON DELETE CASCADE, 
	FOREIGN KEY(request_number) REFERENCES requests (request_number) ON DELETE CASCADE
);

CREATE INDEX ix_shift_assignments_id ON shift_assignments (id);
CREATE INDEX ix_shift_assignments_assigned_at ON shift_assignments (assigned_at);
CREATE INDEX ix_shift_assignments_shift_id ON shift_assignments (shift_id);
CREATE INDEX ix_shift_assignments_request_number ON shift_assignments (request_number);

