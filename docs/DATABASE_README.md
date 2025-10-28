# 📚 UK Management Bot - Database Documentation Index

**Last Updated**: 16 октября 2025
**Status**: ✅ Verified & Corrected
**Version**: 2.2

---

## 🎯 Quick Start

### Automated Startup (Recommended)

**Complete fresh start** with clean database and admin auto-creation:

```bash
# 1. Initialize environment (creates .env from env.copy.dev)
make init

# 2. Start all services (creates database, applies schema, creates admin)
make start
```

**What happens automatically**:
- ✅ PostgreSQL database created with 27 tables
- ✅ 3 ENUM types created (accesslevel, documenttype, verificationstatus)
- ✅ Admin user auto-created from `ADMIN_USER_IDS` in .env
- ✅ Admin gets **all three roles**: applicant, executor, manager
- ✅ Admin has status `approved` (ready to use immediately)
- ✅ Redis cache initialized
- ✅ Media service tables created

**Admin User Configuration**:
- Created from `ADMIN_USER_IDS=48617336` in .env
- Status: `approved` (not "active" - this is important!)
- Roles: `"applicant,executor,manager"` (CSV string format)
- Active Role: `manager`
- Phone: `+998000000000` (placeholder, no address requirement)
- Verification: `approved`

### Manual Database Setup

**Use these files** if you need manual setup:
1. ✅ [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) - **Verified schema documentation**
2. ✅ [database_schema_actual.sql](database_schema_actual.sql) - **Correct SQL DDL**

**Method 1: Using SQLAlchemy (Recommended)**
```python
from uk_management_bot.database.session import Base, engine
import uk_management_bot.database.models

Base.metadata.create_all(bind=engine)
```

**Method 2: Using SQL DDL**
```bash
psql -U uk_bot -d uk_management < database_schema_actual.sql
```

**⚠️ Note about ENUM Types**: The SQL DDL file includes CREATE TYPE statements for PostgreSQL enums:
- `accesslevel` - Used in access_rights.access_level
- `documenttype` - Used in user_documents.document_type
- `verificationstatus` - Used in user_documents.verification_status and user_verifications.status

These types are automatically created when using Method 1 (SQLAlchemy).

### For Understanding the System

**Read in this order**:
1. [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) - Complete schema reference
2. [DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md) - What was wrong and why
3. [DATABASE_ACTION_PLAN.md](DATABASE_ACTION_PLAN.md) - Improvement roadmap
4. [DATABASE_RECOMMENDATIONS.md](DATABASE_RECOMMENDATIONS.md) - Performance optimization

---

## 📁 File Directory

### ✅ Verified & Accurate (Use These!)

| File | Purpose | Status | Size |
|------|---------|--------|------|
| **[DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md)** | Complete schema documentation from ORM | ✅ Verified | 23 tables |
| **[database_schema_actual.sql](database_schema_actual.sql)** | SQL DDL generated from SQLAlchemy | ✅ Verified | ~2000 lines |
| **[DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md)** | List of discrepancies found | ✅ Complete | Analysis |
| **[DATABASE_ACTION_PLAN.md](DATABASE_ACTION_PLAN.md)** | Roadmap for improvements | ✅ Ready | 4-week plan |
| **[DATABASE_RECOMMENDATIONS.md](DATABASE_RECOMMENDATIONS.md)** | Performance optimization guide | ⚠️ Needs update | Mostly valid |
| **[scripts/export_schema.py](scripts/export_schema.py)** | Schema export utility | ✅ Working | Automated |

### ⚠️ Outdated (Don't Use for Setup!)

| File | Status | Issues | Use For |
|------|--------|--------|---------|
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | ⚠️ Partially outdated | 5 tables incorrect | Reference only (75% accurate) |
| [database_schema.sql](database_schema.sql) | ⚠️ Partially outdated | 5 tables incorrect DDL | **DO NOT USE for setup!** |
| [DATABASE_ER_DIAGRAM.md](DATABASE_ER_DIAGRAM.md) | ⚠️ Partially outdated | Incorrect FK relationships | Reference only |

---

## 🔍 What's Verified

### ✅ 100% Accurate (15/20 tables)

These tables are correctly documented in ALL files:

**Core Tables**:
- ✅ `users` - User management with multi-role system
- ✅ `requests` - Request tracking (request_number PRIMARY KEY)
- ✅ `shifts` - Shift management with analytics
- ✅ `shift_templates` - Shift templates for automation
- ✅ `shift_assignments` - Request-to-shift assignments with AI scores
- ✅ `shift_transfers` - Shift transfer system

**Address Directory**:
- ✅ `yards` - Territory zones
- ✅ `buildings` - Buildings in yards
- ✅ `apartments` - Apartments in buildings
- ✅ `user_apartments` - User-apartment many-to-many with moderation
- ✅ `user_yards` - Additional yard coverage for executors

**Verification System**:
- ✅ `user_documents` - User document uploads
- ✅ `user_verifications` - Verification process tracking

**Auxiliary Tables**:
- ✅ `request_comments` - Request comments and history
- ✅ `request_assignments` - Request assignment tracking (legacy)
- ✅ `ratings` - Request ratings
- ✅ `notifications` - User notifications
- ✅ `audit_logs` - Audit trail

### ⚠️ Incorrect in Old Docs (5/20 tables)

These tables have **significant discrepancies** in outdated docs:

1. **`access_rights`** - [CRITICAL]
   - ❌ Old docs: FK to apartments/buildings/yards
   - ✅ Reality: String fields (apartment_number, house_number, yard_name) without FK
   - Missing fields: `is_active`, `expires_at`, `notes`

2. **`quarterly_plans`** - [CRITICAL]
   - ❌ Old docs: 3 basic fields (year, quarter, status)
   - ✅ Reality: 24 fields including dates, metrics, settings
   - Missing: start_date, end_date, specializations, 15+ other fields

3. **`quarterly_shift_schedules`** - [CRITICAL]
   - ❌ Old docs: 5 fields (basic schedule info)
   - ✅ Reality: 16 fields including detailed planning data
   - Missing: assigned_user_id, specialization, schedule_type, 10+ fields

4. **`shift_schedules`** - [CRITICAL]
   - ❌ Old docs: shift_id + user_id + date linkage table
   - ✅ Reality: Analytical table with JSON coverage metrics
   - Completely different purpose and structure!

5. **`planning_conflicts`** - [HIGH]
   - ❌ Old docs: 4 basic fields
   - ✅ Reality: 17 fields with detailed conflict tracking
   - Missing: involved_schedule_ids, conflict_details, 10+ fields

---

## 🎓 Understanding the Documentation

### Schema Evolution

The database schema evolved through **16 manual migrations**:

```
1. replace_request_id.py      - Changed PRIMARY KEY from INTEGER to VARCHAR
2. add_user_roles_active_role.py - Multi-role system
3. add_user_verification_tables.py - Verification system
4. add_address_directory.py    - Address hierarchy
5. add_quarterly_planning_tables.py - Quarterly planning
6. add_advanced_shift_features.py - Enhanced shifts
... and 10 more
```

See [uk_management_bot/database/migrations/](uk_management_bot/database/migrations/) for all scripts.

### Why Discrepancies Happened

1. **Assumptions**: Created docs based on typical patterns without reading all models
2. **Partial Analysis**: Read core models but skipped specialized ones
3. **Ignored Migrations**: Didn't check for existing migration scripts
4. **No Verification**: Didn't export schema from SQLAlchemy to verify

### How It Was Fixed

1. ✅ Read **all** SQLAlchemy models completely
2. ✅ Created [scripts/export_schema.py](scripts/export_schema.py) to export from ORM
3. ✅ Generated [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) and [database_schema_actual.sql](database_schema_actual.sql)
4. ✅ Documented all discrepancies in [DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md)
5. ✅ Created action plan in [DATABASE_ACTION_PLAN.md](DATABASE_ACTION_PLAN.md)

---

## 🚀 Common Tasks

### Complete Fresh Start (Verified Procedure)

```bash
# Stop all containers and remove volumes
docker-compose -f docker-compose.unified.yml down -v

# Initialize environment
make init

# Start all services (auto-creates database + admin)
make start

# Verify everything is running
docker-compose -f docker-compose.unified.yml ps

# Check logs
docker-compose -f docker-compose.unified.yml logs bot | grep -E "(Database|Admin|✅)"
```

**Expected output**:
```
✅ Database engine initialized
✅ ENUM type accesslevel ready
✅ ENUM type documenttype ready
✅ ENUM type verificationstatus ready
✅ All tables created successfully (27 tables)
✅ Admin user created/updated: 48617336
```

### Export Fresh Schema

```bash
# In Docker container
docker-compose -f docker-compose.unified.yml exec bot python /app/scripts/export_schema.py

# Copy to host
docker cp uk-bot:/app/DATABASE_SCHEMA_ACTUAL.md ./
docker cp uk-bot:/app/database_schema_actual.sql ./
```

### Create Database from Scratch (Manual)

```bash
# Method 1: SQLAlchemy (Recommended - used by make start)
docker-compose -f docker-compose.unified.yml exec bot python -c "
from uk_management_bot.database.session import Base, engine
import uk_management_bot.database.models
Base.metadata.create_all(bind=engine)
print('✅ Database created!')
"

# Method 2: SQL DDL
docker-compose -f docker-compose.unified.yml exec -T postgres psql -U uk_bot -d uk_management < database_schema_actual.sql
```

### Verify Admin User After Startup

```bash
# Connect to database
docker-compose -f docker-compose.unified.yml exec postgres psql -U uk_bot -d uk_management

# Check admin user
SELECT id, telegram_id, username, status, roles, active_role, verification_status
FROM users WHERE telegram_id = 48617336;

# Expected result:
# status = 'approved'
# roles = 'applicant,executor,manager'
# active_role = 'manager'
# verification_status = 'approved'
```

### Verify Schema

```python
from uk_management_bot.database.session import Base, engine
from sqlalchemy import inspect

inspector = inspect(engine)

# Get all tables
tables = inspector.get_table_names()
print(f"Tables in DB: {len(tables)}")

# Get all tables from ORM
orm_tables = Base.metadata.tables.keys()
print(f"Tables in ORM: {len(orm_tables)}")

# Compare
missing_in_db = set(orm_tables) - set(tables)
extra_in_db = set(tables) - set(orm_tables)

if missing_in_db:
    print(f"❌ Missing in DB: {missing_in_db}")
if extra_in_db:
    print(f"⚠️ Extra in DB: {extra_in_db}")
if not (missing_in_db or extra_in_db):
    print("✅ Schema is synchronized!")
```

---

## �� Statistics

### Overall Accuracy

| Metric | Value |
|--------|-------|
| **Total Tables** | 23 |
| **Correctly Documented** | 18 tables (78%) |
| **Incorrect in Old Docs** | 5 tables (22%) |
| **Total Fields** | ~300+ |
| **Missing Fields in Old Docs** | 50+ |
| **Incorrect Relationships** | 3 (access_rights FK) |

### File Status

| Type | Total | Accurate | Outdated |
|------|-------|----------|----------|
| **Markdown Docs** | 5 | 2 (40%) | 3 (60%) |
| **SQL Scripts** | 2 | 1 (50%) | 1 (50%) |
| **Utilities** | 1 | 1 (100%) | 0 (0%) |

---

## 🔗 Related Documentation

### In This Repository

- [CLAUDE.md](CLAUDE.md) - Project overview and guidelines
- [MemoryBank/](MemoryBank/) - Project context and state
- [uk_management_bot/database/models/](uk_management_bot/database/models/) - Actual ORM models
- [uk_management_bot/database/migrations/](uk_management_bot/database/migrations/) - Migration scripts

### External Resources

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL 15 Documentation](https://www.postgresql.org/docs/15/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)

---

## ⚡ Quick Reference

### Table Categories

**Core System** (5 tables):
- users, requests, shifts, shift_templates, shift_assignments

**Address System** (6 tables):
- yards, buildings, apartments, user_apartments, user_yards, access_rights

**Shift Management** (4 tables):
- shifts, shift_templates, shift_assignments, shift_transfers

**Planning System** (4 tables):
- quarterly_plans, quarterly_shift_schedules, shift_schedules, planning_conflicts

**Verification** (3 tables):
- user_documents, user_verifications, access_rights

**Auxiliary** (6 tables):
- request_comments, request_assignments, ratings, notifications, audit_logs, shift_transfers

### Critical Tables

**Must understand first**:
1. `users` - Multi-role system (applicant, executor, manager)
2. `requests` - request_number (VARCHAR) as PRIMARY KEY
3. `shifts` - Shift management with analytics
4. `apartments` - Address hierarchy endpoint

**Complex structures**:
- `shift_schedules` - Analytical table with JSON coverage data
- `quarterly_plans` - Full planning system with 24 fields
- `shift_assignments` - AI-powered assignment with scores

---

## 🛠️ Maintenance

### Keep Documentation Synced

**Automated**:
```bash
# Add to .git/hooks/pre-commit
python scripts/export_schema.py
git add DATABASE_SCHEMA_ACTUAL.md database_schema_actual.sql
```

**Manual**:
```bash
# After modifying models
docker-compose -f docker-compose.unified.yml exec bot python /app/scripts/export_schema.py
docker cp uk-bot:/app/DATABASE_SCHEMA_ACTUAL.md ./
docker cp uk-bot:/app/database_schema_actual.sql ./
git add DATABASE_SCHEMA_ACTUAL.md database_schema_actual.sql
git commit -m "docs: update database schema"
```

### Before Making Schema Changes

1. ✅ Read [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md)
2. ✅ Check [DATABASE_ACTION_PLAN.md](DATABASE_ACTION_PLAN.md) for planned changes
3. ✅ Consider migration strategy
4. ✅ Update documentation after changes

---

## 📞 Support

### Found an Issue?

1. Check [DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md) - might be known
2. Verify against actual models in `uk_management_bot/database/models/`
3. Run `scripts/export_schema.py` to get fresh export
4. Compare with documentation

### Need to Update Documentation?

1. Modify SQLAlchemy models in `uk_management_bot/database/models/`
2. Run `scripts/export_schema.py` to regenerate docs
3. Review changes in [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md)
4. Commit updated documentation

---

## 🔧 Troubleshooting

### Admin Can't Access Bot After Startup

**Problem**: Admin user created but can't enter bot after `/start`

**Solution**: Check user status in database:
```sql
SELECT id, telegram_id, status, roles, verification_status
FROM users WHERE telegram_id = 48617336;
```

**Expected values**:
- `status` = `"approved"` (not "active"!)
- `roles` = `"applicant,executor,manager"`
- `verification_status` = `"approved"`

If status is wrong, update with:
```sql
UPDATE users
SET status = 'approved',
    verification_status = 'approved',
    phone = '+998000000000'
WHERE telegram_id = 48617336;
```

### Role Selection Button Not Appearing

**Problem**: "🔀 Выбрать роль" button doesn't appear or appears inconsistently

**Root Cause**: User has multiple roles but system can't parse them correctly

**Solution**: Roles must be in **CSV string format**, not JSON:
```
✅ CORRECT: "applicant,executor,manager"
❌ WRONG:   ["applicant","executor","manager"]
```

Check current format:
```sql
SELECT telegram_id, roles, active_role FROM users WHERE telegram_id = 48617336;
```

If roles are in JSON format, convert to CSV:
```sql
UPDATE users
SET roles = 'applicant,executor,manager'
WHERE telegram_id = 48617336;
```

**Code Implementation**: Use `parse_roles_safe()` from `uk_management_bot/utils/auth_helpers.py` which supports both CSV and JSON formats for backward compatibility.

### Missing Admin Menu Button

**Problem**: "🔧 Админ панель" button missing from main menu

**Checklist**:
1. User must have `manager` role in roles list
2. User status must be `approved`
3. User telegram_id must be in `ADMIN_USER_IDS` env variable
4. Active role should be set (defaults to first role if not set)

**Verify**:
```sql
SELECT telegram_id, roles, active_role, status
FROM users WHERE telegram_id = 48617336;
```

**Environment check**:
```bash
docker-compose -f docker-compose.unified.yml exec bot env | grep ADMIN_USER_IDS
# Should output: ADMIN_USER_IDS=48617336
```

### ENUM Type Already Exists Error

**Problem**: `ERROR: type "accesslevel" already exists` when running schema

**Cause**: Trying to create ENUM types that already exist in database

**Solution**:
```sql
-- Check existing ENUM types
SELECT typname FROM pg_type WHERE typcategory = 'E';

-- If you need to recreate, drop old types first (dangerous!)
DROP TYPE IF EXISTS accesslevel CASCADE;
DROP TYPE IF EXISTS documenttype CASCADE;
DROP TYPE IF EXISTS verificationstatus CASCADE;
```

**Better approach**: Use SQLAlchemy `Base.metadata.create_all()` which handles existing types gracefully.

### Database Connection Refused

**Problem**: `FATAL: password authentication failed for user "uk_bot"`

**Solution**: Check environment variables match between .env and docker-compose:
```bash
# In .env
DATABASE_URL=postgresql://uk_bot:uk_bot_password@postgres:5432/uk_management
POSTGRES_USER=uk_bot
POSTGRES_PASSWORD=uk_bot_password
POSTGRES_DB=uk_management
```

**Restart with clean volumes** if passwords were changed:
```bash
docker-compose -f docker-compose.unified.yml down -v
make start
```

---

## ✅ Checklist

### Before Using Documentation

- [ ] Read this README completely
- [ ] Understand which files are accurate vs outdated
- [ ] Check [DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md) for known issues
- [ ] Use [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) as reference

### Before Creating Database

- [ ] Use **database_schema_actual.sql** or `Base.metadata.create_all()`
- [ ] **DO NOT** use old `database_schema.sql`
- [ ] Verify schema after creation
- [ ] Run migrations if needed

### Before Making Changes

- [ ] Read current schema in [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md)
- [ ] Plan migration strategy
- [ ] Test in development first
- [ ] Update documentation after changes

---

## 🎯 Next Steps

See [DATABASE_ACTION_PLAN.md](DATABASE_ACTION_PLAN.md) for:
- Week 1: Fix outdated documentation
- Week 2: Document migration scripts
- Week 3: Implement Alembic
- Week 4: Automate synchronization

---

**Document Created**: 15 октября 2025
**Last Updated**: 16 октября 2025
**Last Verified**: 16 октября 2025 (Startup procedure tested with make init && make start)
**Maintainer**: Development Team
**Status**: ✅ Current & Accurate

### Recent Updates
- **16.10.2025**: Added automated startup procedure (`make init` + `make start`)
- **16.10.2025**: Documented admin auto-creation from ADMIN_USER_IDS
- **16.10.2025**: Added troubleshooting section for role parsing (CSV vs JSON)
- **16.10.2025**: Added admin verification commands and expected outputs
- **15.10.2025**: Initial schema verification and documentation
