# 🗄️ UK Management Bot - Actual Database Schema

**Generated from**: SQLAlchemy ORM Models
**Date**: 2025-10-15
**Status**: ✅ Verified Against Source Code

---

## ⚠️ Important Notes

### PostgreSQL ENUM Types

This schema uses **3 PostgreSQL ENUM types** defined in [database_schema_actual.sql](database_schema_actual.sql):

1. **`accesslevel`** - Values: `apartment`, `house`, `yard`
   - Used in: `access_rights.access_level`

2. **`documenttype`** - Values: `passport`, `property_deed`, `rental_agreement`, `utility_bill`, `other`
   - Used in: `user_documents.document_type`

3. **`verificationstatus`** - Values: `pending`, `approved`, `rejected`, `requested`
   - Used in: `user_documents.verification_status`, `user_verifications.status`

**Note**: In this documentation, ENUM columns may appear as VARCHAR types. Refer to the actual models in [uk_management_bot/database/models/user_verification.py](uk_management_bot/database/models/user_verification.py) for enum definitions.

---

## 📊 Tables Overview

**Total tables**: 23

- `access_rights`
- `apartments`
- `audit_logs`
- `buildings`
- `notifications`
- `planning_conflicts`
- `quarterly_plans`
- `quarterly_shift_schedules`
- `ratings`
- `request_assignments`
- `request_comments`
- `requests`
- `shift_assignments`
- `shift_schedules`
- `shift_templates`
- `shift_transfers`
- `shifts`
- `user_apartments`
- `user_documents`
- `user_verifications`
- `user_yards`
- `users`
- `yards`

---

## Table: `access_rights`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `access_level` | VARCHAR(9) | NOT NULL | - |  |
| `apartment_number` | VARCHAR(20) | NULL | - |  |
| `house_number` | VARCHAR(20) | NULL | - |  |
| `yard_name` | VARCHAR(100) | NULL | - |  |
| `is_active` | BOOLEAN | NULL | True |  |
| `expires_at` | DATETIME | NULL | - |  |
| `granted_by` | INTEGER | NOT NULL | - | 🔗 FK |
| `granted_at` | DATETIME | NULL | - |  |
| `notes` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `user_id` → `users.id`
- `granted_by` → `users.id`

### Indexes

- `ix_access_rights_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (granted_by)
- `None`: ForeignKeyConstraint on (user_id)

---

## Table: `apartments`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `building_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `apartment_number` | VARCHAR(20) | NOT NULL | - |  |
| `entrance` | INTEGER | NULL | - |  |
| `floor` | INTEGER | NULL | - |  |
| `rooms_count` | INTEGER | NULL | - |  |
| `area` | FLOAT | NULL | - |  |
| `description` | TEXT | NULL | - |  |
| `is_active` | BOOLEAN | NOT NULL | True |  |
| `created_at` | DATETIME | NULL | - |  |
| `created_by` | INTEGER | NULL | - | 🔗 FK |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `created_by` → `users.id`
- `building_id` → `buildings.id`

### Indexes

- `ix_apartments_id` on (id) 
- `ix_apartments_apartment_number` on (apartment_number) 
- `ix_apartments_building_id` on (building_id) 
- `ix_apartments_is_active` on (is_active) 

### Constraints

- `None`: ForeignKeyConstraint on (building_id)
- `None`: ForeignKeyConstraint on (created_by)
- `None`: PrimaryKeyConstraint on (id)
- `uix_building_apartment`: UniqueConstraint on (building_id, apartment_number)

---

## Table: `audit_logs`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NULL | - | 🔗 FK |
| `telegram_user_id` | INTEGER | NULL | - |  |
| `action` | VARCHAR(100) | NOT NULL | - |  |
| `details` | JSON | NULL | - |  |
| `ip_address` | VARCHAR(45) | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `user_id` → `users.id`

### Indexes

- `ix_audit_logs_telegram_user_id` on (telegram_user_id) 
- `ix_audit_logs_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: PrimaryKeyConstraint on (id)

---

## Table: `buildings`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `address` | VARCHAR(300) | NOT NULL | - |  |
| `yard_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `gps_latitude` | FLOAT | NULL | - |  |
| `gps_longitude` | FLOAT | NULL | - |  |
| `entrance_count` | INTEGER | NOT NULL | 1 |  |
| `floor_count` | INTEGER | NOT NULL | 1 |  |
| `description` | TEXT | NULL | - |  |
| `is_active` | BOOLEAN | NOT NULL | True |  |
| `created_at` | DATETIME | NULL | - |  |
| `created_by` | INTEGER | NULL | - | 🔗 FK |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `yard_id` → `yards.id`
- `created_by` → `users.id`

### Indexes

- `ix_buildings_is_active` on (is_active) 
- `ix_buildings_id` on (id) 
- `ix_buildings_address` on (address) 
- `ix_buildings_yard_id` on (yard_id) 

### Constraints

- `None`: ForeignKeyConstraint on (yard_id)
- `None`: ForeignKeyConstraint on (created_by)
- `None`: PrimaryKeyConstraint on (id)

---

## Table: `notifications`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `notification_type` | VARCHAR(50) | NOT NULL | - |  |
| `title` | VARCHAR(255) | NULL | - |  |
| `content` | TEXT | NOT NULL | - |  |
| `is_read` | BOOLEAN | NULL | False |  |
| `is_sent` | BOOLEAN | NULL | False |  |
| `meta_data` | JSON | NULL | <function dict at 0xffffb39da980> |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `user_id` → `users.id`

### Indexes

- `ix_notifications_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: PrimaryKeyConstraint on (id)

---

## Table: `planning_conflicts`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `quarterly_plan_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `conflict_type` | VARCHAR(100) | NOT NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | pending |  |
| `involved_schedule_ids` | JSON | NULL | - |  |
| `involved_user_ids` | JSON | NULL | - |  |
| `conflict_time` | DATETIME | NULL | - |  |
| `conflict_date` | DATE | NULL | - |  |
| `conflict_details` | JSON | NULL | - |  |
| `description` | TEXT | NULL | - |  |
| `suggested_resolutions` | JSON | NULL | - |  |
| `applied_resolution` | JSON | NULL | - |  |
| `resolved_at` | DATETIME | NULL | - |  |
| `resolved_by` | INTEGER | NULL | - | 🔗 FK |
| `priority` | INTEGER | NOT NULL | 1 |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `resolved_by` → `users.id`
- `quarterly_plan_id` → `quarterly_plans.id`

### Indexes

- `ix_planning_conflicts_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (quarterly_plan_id)
- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (resolved_by)

---

## Table: `quarterly_plans`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `year` | INTEGER | NOT NULL | - |  |
| `quarter` | INTEGER | NOT NULL | - |  |
| `start_date` | DATE | NOT NULL | - |  |
| `end_date` | DATE | NOT NULL | - |  |
| `created_by` | INTEGER | NOT NULL | - | 🔗 FK |
| `status` | VARCHAR(50) | NOT NULL | draft |  |
| `specializations` | JSON | NULL | - |  |
| `coverage_24_7` | BOOLEAN | NOT NULL | False |  |
| `load_balancing_enabled` | BOOLEAN | NOT NULL | True |  |
| `auto_transfers_enabled` | BOOLEAN | NOT NULL | True |  |
| `notifications_enabled` | BOOLEAN | NOT NULL | True |  |
| `total_shifts_planned` | INTEGER | NOT NULL | 0 |  |
| `total_hours_planned` | FLOAT | NOT NULL | 0.0 |  |
| `coverage_percentage` | FLOAT | NOT NULL | 0.0 |  |
| `total_conflicts` | INTEGER | NOT NULL | 0 |  |
| `resolved_conflicts` | INTEGER | NOT NULL | 0 |  |
| `pending_conflicts` | INTEGER | NOT NULL | 0 |  |
| `settings` | JSON | NULL | - |  |
| `notes` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |
| `activated_at` | DATETIME | NULL | - |  |
| `archived_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `created_by` → `users.id`

### Indexes

- `ix_quarterly_plans_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (created_by)

---

## Table: `quarterly_shift_schedules`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `quarterly_plan_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `planned_date` | DATE | NOT NULL | - |  |
| `planned_start_time` | DATETIME | NOT NULL | - |  |
| `planned_end_time` | DATETIME | NOT NULL | - |  |
| `assigned_user_id` | INTEGER | NULL | - | 🔗 FK |
| `specialization` | VARCHAR(100) | NOT NULL | - |  |
| `schedule_type` | VARCHAR(50) | NOT NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | planned |  |
| `actual_shift_id` | INTEGER | NULL | - | 🔗 FK |
| `shift_config` | JSON | NULL | - |  |
| `coverage_areas` | JSON | NULL | - |  |
| `priority` | INTEGER | NOT NULL | 1 |  |
| `notes` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `actual_shift_id` → `shifts.id`
- `quarterly_plan_id` → `quarterly_plans.id`
- `assigned_user_id` → `users.id`

### Indexes

- `ix_quarterly_shift_schedules_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (quarterly_plan_id)
- `None`: ForeignKeyConstraint on (actual_shift_id)
- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (assigned_user_id)

---

## Table: `ratings`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `request_number` | VARCHAR(10) | NOT NULL | - | 🔗 FK |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `rating` | INTEGER | NOT NULL | - |  |
| `review` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `request_number` → `requests.request_number`
- `user_id` → `users.id`

### Indexes

- `ix_ratings_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (user_id)
- `None`: ForeignKeyConstraint on (request_number)

---

## Table: `request_assignments`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `request_number` | VARCHAR(10) | NOT NULL | - | 🔗 FK |
| `assignment_type` | VARCHAR(20) | NOT NULL | - |  |
| `group_specialization` | VARCHAR(100) | NULL | - |  |
| `executor_id` | INTEGER | NULL | - | 🔗 FK |
| `status` | VARCHAR(20) | NULL | active |  |
| `created_at` | DATETIME | NULL | - |  |
| `created_by` | INTEGER | NOT NULL | - | 🔗 FK |

### Foreign Keys

- `executor_id` → `users.id`
- `created_by` → `users.id`
- `request_number` → `requests.request_number`

### Indexes

- `ix_request_assignments_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (request_number)
- `None`: ForeignKeyConstraint on (executor_id)
- `None`: ForeignKeyConstraint on (created_by)

---

## Table: `request_comments`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `request_number` | VARCHAR(10) | NOT NULL | - | 🔗 FK |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `comment_text` | TEXT | NOT NULL | - |  |
| `comment_type` | VARCHAR(50) | NOT NULL | - |  |
| `previous_status` | VARCHAR(50) | NULL | - |  |
| `new_status` | VARCHAR(50) | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `request_number` → `requests.request_number`
- `user_id` → `users.id`

### Indexes

- `ix_request_comments_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (request_number)

---

## Table: `requests`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `request_number` | VARCHAR(10) | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `category` | VARCHAR(100) | NOT NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | Новая |  |
| `address` | TEXT | NULL | - |  |
| `description` | TEXT | NOT NULL | - |  |
| `apartment` | VARCHAR(20) | NULL | - |  |
| `urgency` | VARCHAR(20) | NOT NULL | Обычная |  |
| `apartment_id` | INTEGER | NULL | - | 🔗 FK |
| `media_files` | JSON | NULL | <function list at 0xffffb3920720> |  |
| `executor_id` | INTEGER | NULL | - | 🔗 FK |
| `notes` | TEXT | NULL | - |  |
| `completion_report` | TEXT | NULL | - |  |
| `completion_media` | JSON | NULL | <function list at 0xffffb39209a0> |  |
| `assignment_type` | VARCHAR(20) | NULL | - |  |
| `assigned_group` | VARCHAR(100) | NULL | - |  |
| `assigned_at` | DATETIME | NULL | - |  |
| `assigned_by` | INTEGER | NULL | - | 🔗 FK |
| `purchase_materials` | TEXT | NULL | - |  |
| `requested_materials` | TEXT | NULL | - |  |
| `manager_materials_comment` | TEXT | NULL | - |  |
| `purchase_history` | TEXT | NULL | - |  |
| `is_returned` | BOOLEAN | NOT NULL | False |  |
| `return_reason` | TEXT | NULL | - |  |
| `return_media` | JSON | NULL | <function list at 0xffffb3920d60> |  |
| `returned_at` | DATETIME | NULL | - |  |
| `returned_by` | INTEGER | NULL | - | 🔗 FK |
| `manager_confirmed` | BOOLEAN | NOT NULL | False |  |
| `manager_confirmed_by` | INTEGER | NULL | - | 🔗 FK |
| `manager_confirmed_at` | DATETIME | NULL | - |  |
| `manager_confirmation_notes` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |
| `completed_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `assigned_by` → `users.id`
- `user_id` → `users.id`
- `executor_id` → `users.id`
- `manager_confirmed_by` → `users.id`
- `apartment_id` → `apartments.id`
- `returned_by` → `users.id`

### Indexes

- `ix_requests_apartment_id` on (apartment_id) 
- `ix_requests_request_number` on (request_number) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: PrimaryKeyConstraint on (request_number)
- `None`: ForeignKeyConstraint on (manager_confirmed_by)
- `None`: ForeignKeyConstraint on (apartment_id)
- `None`: ForeignKeyConstraint on (executor_id)
- `None`: ForeignKeyConstraint on (returned_by)
- `None`: ForeignKeyConstraint on (assigned_by)

---

## Table: `shift_assignments`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `shift_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `request_number` | VARCHAR(10) | NOT NULL | - | 🔗 FK |
| `assignment_priority` | INTEGER | NOT NULL | 1 |  |
| `estimated_duration` | INTEGER | NULL | - |  |
| `assignment_order` | INTEGER | NULL | - |  |
| `ai_score` | FLOAT | NULL | - |  |
| `confidence_level` | FLOAT | NULL | - |  |
| `specialization_match_score` | FLOAT | NULL | - |  |
| `geographic_score` | FLOAT | NULL | - |  |
| `workload_score` | FLOAT | NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | assigned |  |
| `auto_assigned` | BOOLEAN | NOT NULL | False |  |
| `confirmed_by_executor` | BOOLEAN | NOT NULL | False |  |
| `assigned_at` | DATETIME | NULL | - |  |
| `started_at` | DATETIME | NULL | - |  |
| `completed_at` | DATETIME | NULL | - |  |
| `planned_start_at` | DATETIME | NULL | - |  |
| `planned_completion_at` | DATETIME | NULL | - |  |
| `assignment_reason` | VARCHAR(200) | NULL | - |  |
| `notes` | TEXT | NULL | - |  |
| `executor_instructions` | TEXT | NULL | - |  |
| `actual_duration` | INTEGER | NULL | - |  |
| `execution_quality_rating` | FLOAT | NULL | - |  |
| `had_issues` | BOOLEAN | NOT NULL | False |  |
| `issues_description` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `shift_id` → `shifts.id`
- `request_number` → `requests.request_number`

### Indexes

- `ix_shift_assignments_id` on (id) 
- `ix_shift_assignments_assigned_at` on (assigned_at) 
- `ix_shift_assignments_shift_id` on (shift_id) 
- `ix_shift_assignments_request_number` on (request_number) 

### Constraints

- `None`: ForeignKeyConstraint on (shift_id)
- `None`: ForeignKeyConstraint on (request_number)
- `None`: PrimaryKeyConstraint on (id)

---

## Table: `shift_schedules`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `date` | DATE | NOT NULL | - | ⭐ UNIQUE |
| `planned_coverage` | JSON | NULL | - |  |
| `actual_coverage` | JSON | NULL | - |  |
| `planned_specialization_coverage` | JSON | NULL | - |  |
| `actual_specialization_coverage` | JSON | NULL | - |  |
| `predicted_requests` | INTEGER | NULL | - |  |
| `actual_requests` | INTEGER | NOT NULL | 0 |  |
| `prediction_accuracy` | FLOAT | NULL | - |  |
| `recommended_shifts` | INTEGER | NULL | - |  |
| `actual_shifts` | INTEGER | NOT NULL | 0 |  |
| `optimization_score` | FLOAT | NULL | - |  |
| `coverage_percentage` | FLOAT | NULL | - |  |
| `load_balance_score` | FLOAT | NULL | - |  |
| `special_conditions` | JSON | NULL | - |  |
| `manual_adjustments` | JSON | NULL | - |  |
| `notes` | VARCHAR(500) | NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | draft |  |
| `created_by` | INTEGER | NULL | - | 🔗 FK |
| `auto_generated` | BOOLEAN | NOT NULL | False |  |
| `version` | INTEGER | NOT NULL | 1 |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `created_by` → `users.id`

### Indexes

- `ix_shift_schedules_date` on (date) UNIQUE
- `ix_shift_schedules_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (created_by)

---

## Table: `shift_templates`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `name` | VARCHAR(100) | NOT NULL | - |  |
| `description` | TEXT | NULL | - |  |
| `start_hour` | INTEGER | NOT NULL | - |  |
| `start_minute` | INTEGER | NOT NULL | 0 |  |
| `duration_hours` | INTEGER | NOT NULL | 8 |  |
| `required_specializations` | JSON | NULL | - |  |
| `min_executors` | INTEGER | NOT NULL | 1 |  |
| `max_executors` | INTEGER | NOT NULL | 3 |  |
| `default_max_requests` | INTEGER | NOT NULL | 10 |  |
| `coverage_areas` | JSON | NULL | - |  |
| `geographic_zone` | VARCHAR(100) | NULL | - |  |
| `priority_level` | INTEGER | NOT NULL | 1 |  |
| `auto_create` | BOOLEAN | NOT NULL | False |  |
| `days_of_week` | JSON | NULL | - |  |
| `advance_days` | INTEGER | NOT NULL | 7 |  |
| `is_active` | BOOLEAN | NOT NULL | True |  |
| `default_shift_type` | VARCHAR(50) | NOT NULL | regular |  |
| `settings` | JSON | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Indexes

- `ix_shift_templates_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)

---

## Table: `shift_transfers`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `shift_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `from_executor_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `to_executor_id` | INTEGER | NULL | - | 🔗 FK |
| `status` | VARCHAR(50) | NOT NULL | pending |  |
| `reason` | VARCHAR(100) | NOT NULL | - |  |
| `comment` | TEXT | NULL | - |  |
| `urgency_level` | VARCHAR(20) | NOT NULL | normal |  |
| `created_at` | DATETIME | NOT NULL | <function datetime.utcnow at 0xffffb39b9940> |  |
| `assigned_at` | DATETIME | NULL | - |  |
| `responded_at` | DATETIME | NULL | - |  |
| `completed_at` | DATETIME | NULL | - |  |
| `auto_assigned` | BOOLEAN | NOT NULL | False |  |
| `retry_count` | INTEGER | NOT NULL | 0 |  |
| `max_retries` | INTEGER | NOT NULL | 3 |  |

### Foreign Keys

- `from_executor_id` → `users.id`
- `shift_id` → `shifts.id`
- `to_executor_id` → `users.id`

### Indexes

- `ix_shift_transfers_to_executor_id` on (to_executor_id) 
- `ix_shift_transfers_shift_id` on (shift_id) 
- `ix_shift_transfers_created_at` on (created_at) 
- `ix_shift_transfers_status` on (status) 
- `ix_shift_transfers_from_executor_id` on (from_executor_id) 
- `ix_shift_transfers_id` on (id) 
- `ix_shift_transfers_reason` on (reason) 
- `ix_shift_transfers_assigned_at` on (assigned_at) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (from_executor_id)
- `None`: ForeignKeyConstraint on (to_executor_id)
- `None`: ForeignKeyConstraint on (shift_id)

---

## Table: `shifts`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NULL | - | 🔗 FK |
| `start_time` | DATETIME | NOT NULL | - |  |
| `end_time` | DATETIME | NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | active |  |
| `notes` | TEXT | NULL | - |  |
| `planned_start_time` | DATETIME | NULL | - |  |
| `planned_end_time` | DATETIME | NULL | - |  |
| `shift_template_id` | INTEGER | NULL | - | 🔗 FK |
| `shift_type` | VARCHAR(50) | NULL | regular |  |
| `specialization_focus` | JSON | NULL | - |  |
| `coverage_areas` | JSON | NULL | - |  |
| `geographic_zone` | VARCHAR(100) | NULL | - |  |
| `max_requests` | INTEGER | NOT NULL | 10 |  |
| `current_request_count` | INTEGER | NOT NULL | 0 |  |
| `priority_level` | INTEGER | NOT NULL | 1 |  |
| `completed_requests` | INTEGER | NOT NULL | 0 |  |
| `average_completion_time` | FLOAT | NULL | - |  |
| `average_response_time` | FLOAT | NULL | - |  |
| `efficiency_score` | FLOAT | NULL | - |  |
| `quality_rating` | FLOAT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `user_id` → `users.id`
- `shift_template_id` → `shift_templates.id`

### Indexes

- `ix_shifts_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: ForeignKeyConstraint on (shift_template_id)
- `None`: PrimaryKeyConstraint on (id)

---

## Table: `user_apartments`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `apartment_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `status` | VARCHAR(20) | NOT NULL | pending |  |
| `requested_at` | DATETIME | NOT NULL | - |  |
| `reviewed_at` | DATETIME | NULL | - |  |
| `reviewed_by` | INTEGER | NULL | - | 🔗 FK |
| `admin_comment` | TEXT | NULL | - |  |
| `is_owner` | BOOLEAN | NOT NULL | False |  |
| `is_primary` | BOOLEAN | NOT NULL | True |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `user_id` → `users.id`
- `reviewed_by` → `users.id`
- `apartment_id` → `apartments.id`

### Indexes

- `ix_user_apartments_apartment_id` on (apartment_id) 
- `ix_user_apartments_user_id` on (user_id) 
- `ix_user_apartments_id` on (id) 
- `ix_user_apartments_status` on (status) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: PrimaryKeyConstraint on (id)
- `uix_user_apartment`: UniqueConstraint on (user_id, apartment_id)
- `None`: ForeignKeyConstraint on (reviewed_by)
- `None`: ForeignKeyConstraint on (apartment_id)

---

## Table: `user_documents`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `document_type` | VARCHAR(16) | NOT NULL | - |  |
| `file_id` | VARCHAR(255) | NOT NULL | - |  |
| `file_name` | VARCHAR(255) | NULL | - |  |
| `file_size` | INTEGER | NULL | - |  |
| `verification_status` | VARCHAR(9) | NULL | VerificationStatus.PENDING |  |
| `verification_notes` | TEXT | NULL | - |  |
| `verified_by` | INTEGER | NULL | - | 🔗 FK |
| `verified_at` | DATETIME | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `verified_by` → `users.id`
- `user_id` → `users.id`

### Indexes

- `ix_user_documents_id` on (id) 

### Constraints

- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (verified_by)
- `None`: ForeignKeyConstraint on (user_id)

---

## Table: `user_verifications`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `status` | VARCHAR(9) | NULL | VerificationStatus.PENDING |  |
| `requested_info` | JSON | NULL | <function dict at 0xffffb380a160> |  |
| `requested_at` | DATETIME | NULL | - |  |
| `requested_by` | INTEGER | NULL | - | 🔗 FK |
| `admin_notes` | TEXT | NULL | - |  |
| `verified_by` | INTEGER | NULL | - | 🔗 FK |
| `verified_at` | DATETIME | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `user_id` → `users.id`
- `verified_by` → `users.id`
- `requested_by` → `users.id`

### Indexes

- `ix_user_verifications_id` on (id) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: ForeignKeyConstraint on (verified_by)
- `None`: ForeignKeyConstraint on (requested_by)
- `None`: PrimaryKeyConstraint on (id)

---

## Table: `user_yards`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `user_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `yard_id` | INTEGER | NOT NULL | - | 🔗 FK |
| `granted_at` | DATETIME | NOT NULL | - |  |
| `granted_by` | INTEGER | NULL | - | 🔗 FK |
| `comment` | TEXT | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `granted_by` → `users.id`
- `user_id` → `users.id`
- `yard_id` → `yards.id`

### Indexes

- `ix_user_yards_id` on (id) 
- `ix_user_yards_user_id` on (user_id) 
- `ix_user_yards_yard_id` on (yard_id) 

### Constraints

- `None`: ForeignKeyConstraint on (user_id)
- `None`: ForeignKeyConstraint on (granted_by)
- `None`: PrimaryKeyConstraint on (id)
- `None`: ForeignKeyConstraint on (yard_id)
- `uix_user_yard`: UniqueConstraint on (user_id, yard_id)

---

## Table: `users`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `telegram_id` | BIGINT | NOT NULL | - | ⭐ UNIQUE |
| `username` | VARCHAR(255) | NULL | - |  |
| `first_name` | VARCHAR(255) | NULL | - |  |
| `last_name` | VARCHAR(255) | NULL | - |  |
| `role` | VARCHAR(50) | NOT NULL | applicant |  |
| `roles` | TEXT | NULL | - |  |
| `active_role` | VARCHAR(50) | NULL | - |  |
| `status` | VARCHAR(50) | NOT NULL | pending |  |
| `language` | VARCHAR(10) | NOT NULL | ru |  |
| `phone` | VARCHAR(20) | NULL | - |  |
| `specialization` | TEXT | NULL | - |  |
| `verification_status` | VARCHAR(50) | NOT NULL | pending |  |
| `verification_notes` | TEXT | NULL | - |  |
| `verification_date` | DATETIME | NULL | - |  |
| `verified_by` | INTEGER | NULL | - |  |
| `passport_series` | VARCHAR(10) | NULL | - |  |
| `passport_number` | VARCHAR(10) | NULL | - |  |
| `birth_date` | DATETIME | NULL | - |  |
| `created_at` | DATETIME | NULL | - |  |
| `updated_at` | DATETIME | NULL | - |  |

### Indexes

- `ix_users_id` on (id) 
- `ix_users_telegram_id` on (telegram_id) UNIQUE

### Constraints

- `None`: PrimaryKeyConstraint on (id)

---

## Table: `yards`

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | - | 🔑 PRIMARY KEY |
| `name` | VARCHAR(200) | NOT NULL | - | ⭐ UNIQUE |
| `description` | TEXT | NULL | - |  |
| `gps_latitude` | FLOAT | NULL | - |  |
| `gps_longitude` | FLOAT | NULL | - |  |
| `is_active` | BOOLEAN | NOT NULL | True |  |
| `created_at` | DATETIME | NULL | - |  |
| `created_by` | INTEGER | NULL | - | 🔗 FK |
| `updated_at` | DATETIME | NULL | - |  |

### Foreign Keys

- `created_by` → `users.id`

### Indexes

- `ix_yards_name` on (name) UNIQUE
- `ix_yards_id` on (id) 
- `ix_yards_is_active` on (is_active) 

### Constraints

- `None`: ForeignKeyConstraint on (created_by)
- `None`: PrimaryKeyConstraint on (id)

---

