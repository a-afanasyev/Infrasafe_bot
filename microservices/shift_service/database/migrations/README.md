# Database Migrations for Shift Service

This directory contains Alembic migrations for the Shift Service database schema.

## 📋 Migrations Overview

### Current Migrations:

1. **2025_10_01_1935_480bc2a7814b** - Initial Shift Service Schema
   - Creates `shifts` table
   - Creates `shift_templates` table
   - Creates `shift_assignments` table
   - Creates `shift_transfers` table
   - Adds all necessary indexes and constraints

## 🚀 Running Migrations

### Apply all pending migrations:

```bash
# In Docker container
docker-compose exec shift-service alembic upgrade head

# Local development
alembic upgrade head
```

### Check current migration status:

```bash
# In Docker container
docker-compose exec shift-service alembic current

# Local development
alembic current
```

### Show migration history:

```bash
alembic history
```

### Rollback one migration:

```bash
alembic downgrade -1
```

### Rollback to specific revision:

```bash
alembic downgrade <revision_id>
```

## 🔧 Creating New Migrations

### Auto-generate migration from model changes:

```bash
# In Docker container
docker-compose exec shift-service alembic revision --autogenerate -m "description_of_changes"

# Local development
alembic revision --autogenerate -m "description_of_changes"
```

### Create empty migration:

```bash
alembic revision -m "description_of_changes"
```

## ✅ Migration Best Practices

1. **Always Review Auto-Generated Migrations**:
   - Alembic may not detect all changes correctly
   - Check for data type changes, constraint changes, etc.

2. **Test Migrations**:
   - Test both `upgrade` and `downgrade` operations
   - Test on a copy of production data

3. **Backup Before Migration**:
   ```bash
   # Backup database
   docker-compose exec shift-db pg_dump -U shift_user shift_db > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

4. **Migration Naming**:
   - Use descriptive names
   - Format: `YYYY_MM_DD_HHMM_revision_description`

5. **Data Migrations**:
   - Keep schema changes separate from data migrations
   - Use separate scripts for large data migrations

## 📊 Schema Overview

### Tables:

- **shifts**: Core shift records
  - Primary key: UUID
  - Indexes on: executor_id, start_time, status, specialization
  - Foreign keys: template_id → shift_templates.id

- **shift_templates**: Reusable shift templates
  - Primary key: UUID
  - Unique constraint on: name
  - Indexes on: specialization, is_active

- **shift_assignments**: Assignment tracking
  - Primary key: UUID
  - Foreign keys: shift_id → shifts.id
  - Indexes on: shift_id, executor_id, is_active

- **shift_transfers**: Transfer workflow tracking
  - Primary key: UUID
  - Foreign keys: shift_id → shifts.id
  - Indexes on: shift_id, status, from_executor_id, to_executor_id

## 🔍 Troubleshooting

### Migration stuck or failed:

```bash
# Check current state
alembic current

# Check alembic_version table
docker-compose exec shift-db psql -U shift_user -d shift_db -c "SELECT * FROM alembic_version;"

# Force set to specific revision (careful!)
alembic stamp <revision_id>
```

### Reset migrations (development only):

```bash
# WARNING: This will delete all data!

# Drop all tables
alembic downgrade base

# Or recreate database
docker-compose down -v
docker-compose up -d shift-db
alembic upgrade head
```

### Check for drift between models and database:

```bash
# Generate migration to see differences
alembic revision --autogenerate -m "check_for_drift"

# Review the generated file - if it's empty, no drift exists
# Delete the file if not needed
```

## 📝 Migration Checklist

Before applying migrations to production:

- [ ] Reviewed migration file
- [ ] Tested upgrade on dev database
- [ ] Tested downgrade on dev database
- [ ] Checked for data loss risks
- [ ] Created database backup
- [ ] Scheduled maintenance window
- [ ] Prepared rollback plan
- [ ] Notified team
- [ ] Documented changes

## 🔗 Related Documentation

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Shift Service README](../../README.md)
