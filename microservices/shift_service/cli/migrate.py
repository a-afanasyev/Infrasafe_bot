#!/usr/bin/env python3
# Migration Management CLI for Shift Service
# UK Management Bot - Shift Service

import asyncio
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.migration_utils import (
    DataMigrationService,
    validate_migration_data,
    execute_migration,
    rollback_migration
)
from config import settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def cmd_validate(args):
    """Validate migration data without executing"""
    logger.info(f"Validating migration data from: {args.source_db}")

    try:
        report = await validate_migration_data(args.source_db)

        print("\n" + "=" * 80)
        print("MIGRATION VALIDATION REPORT")
        print("=" * 80)
        print(f"Total Records: {report['total_records']}")
        print(f"Validation Errors: {len(report['errors'])}")

        if report['errors']:
            print("\nErrors:")
            for error in report['errors'][:20]:  # Show first 20 errors
                print(f"  - {error}")
            if len(report['errors']) > 20:
                print(f"  ... and {len(report['errors']) - 20} more errors")

            sys.exit(1)
        else:
            print("\n✅ Validation passed! Data is ready for migration.")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


async def cmd_migrate(args):
    """Execute migration"""
    logger.info(f"Starting migration from: {args.source_db}")

    if not args.force:
        print("\n" + "!" * 80)
        print("WARNING: This will migrate data to the Shift Service database.")
        print(f"Source: {args.source_db}")
        print(f"Target: {settings.database_url}")
        print("!" * 80)

        confirm = input("\nType 'yes' to continue: ")
        if confirm.lower() != 'yes':
            print("Migration cancelled.")
            sys.exit(0)

    try:
        report = await execute_migration(args.source_db)

        print("\n" + "=" * 80)
        print("MIGRATION REPORT")
        print("=" * 80)
        print(f"Started At: {report['started_at']}")
        print(f"Total Records: {report['total_records']}")
        print(f"Migrated Records: {report['migrated_records']}")
        print(f"Failed Records: {report['failed_records']}")
        print(f"Completed At: {report['completed_at']}")

        if report['rollback_data_file']:
            print(f"\n💾 Rollback File: {report['rollback_data_file']}")
            print("Use this file to rollback migration if needed")

        if report['errors']:
            print(f"\n⚠️  Errors ({len(report['errors'])}):")
            for error in report['errors'][:10]:
                print(f"  - {error}")
            if len(report['errors']) > 10:
                print(f"  ... and {len(report['errors']) - 10} more errors")

        if report['failed_records'] > 0:
            print(f"\n❌ Migration completed with {report['failed_records']} failures")
            sys.exit(1)
        else:
            print("\n✅ Migration completed successfully!")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


async def cmd_rollback(args):
    """Rollback migration using rollback file"""
    logger.info(f"Starting rollback from file: {args.rollback_file}")

    if not args.force:
        print("\n" + "!" * 80)
        print("WARNING: This will delete migrated data from Shift Service database.")
        print(f"Rollback File: {args.rollback_file}")
        print("!" * 80)

        confirm = input("\nType 'yes' to continue: ")
        if confirm.lower() != 'yes':
            print("Rollback cancelled.")
            sys.exit(0)

    try:
        report = await rollback_migration(args.rollback_file)

        print("\n" + "=" * 80)
        print("ROLLBACK REPORT")
        print("=" * 80)
        print(f"Started At: {report['started_at']}")
        print(f"Records Processed: {report['records_processed']}")
        print(f"Records Deleted: {report['records_deleted']}")
        print(f"Completed At: {report['completed_at']}")

        if report['errors']:
            print(f"\n⚠️  Errors ({len(report['errors'])}):")
            for error in report['errors']:
                print(f"  - {error}")
            sys.exit(1)
        else:
            print("\n✅ Rollback completed successfully!")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        sys.exit(1)


async def cmd_check_schema(args):
    """Check database schema status"""
    from database import check_database_connection
    from sqlalchemy import inspect
    from database import engine

    logger.info("Checking database schema...")

    try:
        # Check connection
        health = await check_database_connection()
        if health["status"] != "healthy":
            print("❌ Database connection failed")
            sys.exit(1)

        # Check tables
        from models import Base

        print("\n" + "=" * 80)
        print("DATABASE SCHEMA STATUS")
        print("=" * 80)
        print(f"Database: {settings.database_url}")
        print(f"Connection: ✅ Healthy")

        expected_tables = {
            'shifts',
            'shift_templates',
            'shift_assignments',
            'shift_transfers',
            'alembic_version'
        }

        # Get actual tables
        async with engine.connect() as conn:
            inspector = inspect(engine.sync_engine)
            actual_tables = set(inspector.get_table_names())

        print(f"\nExpected Tables: {len(expected_tables)}")
        print(f"Actual Tables: {len(actual_tables)}")

        missing = expected_tables - actual_tables
        extra = actual_tables - expected_tables

        if missing:
            print(f"\n⚠️  Missing Tables ({len(missing)}):")
            for table in sorted(missing):
                print(f"  - {table}")

        if extra:
            print(f"\n➕ Extra Tables ({len(extra)}):")
            for table in sorted(extra):
                print(f"  - {table}")

        if not missing and not extra:
            print("\n✅ All expected tables present")

        # Check alembic version
        from sqlalchemy import text
        async with engine.connect() as conn:
            try:
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                print(f"\nAlembic Version: {version}")
            except:
                print("\n⚠️  No alembic_version found - migrations not applied")

        sys.exit(0 if not missing else 1)

    except Exception as e:
        logger.error(f"Schema check failed: {e}")
        sys.exit(1)


async def cmd_validate_integrity(args):
    """Validate data integrity after migration"""
    from sqlalchemy import select, func, text
    from database import AsyncSessionLocal
    from models.shifts import Shift, ShiftTemplate, ShiftTransfer, ShiftAssignment

    logger.info("Validating data integrity...")

    try:
        async with AsyncSessionLocal() as db:
            issues = []

            # Check 1: Shifts with invalid time ranges
            result = await db.execute(
                select(func.count(Shift.id)).where(Shift.start_time >= Shift.end_time)
            )
            invalid_times = result.scalar()
            if invalid_times > 0:
                issues.append(f"❌ {invalid_times} shifts with invalid time ranges")

            # Check 2: Shifts with invalid duration
            result = await db.execute(
                select(func.count(Shift.id)).where(Shift.duration_hours <= 0)
            )
            invalid_duration = result.scalar()
            if invalid_duration > 0:
                issues.append(f"❌ {invalid_duration} shifts with invalid duration")

            # Check 3: Shifts with invalid priority
            result = await db.execute(
                select(func.count(Shift.id)).where(
                    (Shift.priority < 1) | (Shift.priority > 4)
                )
            )
            invalid_priority = result.scalar()
            if invalid_priority > 0:
                issues.append(f"❌ {invalid_priority} shifts with invalid priority")

            # Check 4: Orphaned shift assignments
            result = await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM shift_assignments sa
                    LEFT JOIN shifts s ON sa.shift_id = s.id
                    WHERE s.id IS NULL
                """)
            )
            orphaned_assignments = result.scalar()
            if orphaned_assignments > 0:
                issues.append(f"❌ {orphaned_assignments} orphaned shift assignments")

            # Check 5: Orphaned transfers
            result = await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM shift_transfers st
                    LEFT JOIN shifts s ON st.shift_id = s.id
                    WHERE s.id IS NULL
                """)
            )
            orphaned_transfers = result.scalar()
            if orphaned_transfers > 0:
                issues.append(f"❌ {orphaned_transfers} orphaned shift transfers")

            # Check 6: Templates with invalid time ranges
            result = await db.execute(
                select(func.count(ShiftTemplate.id)).where(
                    ShiftTemplate.start_time >= ShiftTemplate.end_time
                )
            )
            invalid_template_times = result.scalar()
            if invalid_template_times > 0:
                issues.append(f"❌ {invalid_template_times} templates with invalid time ranges")

            # Summary
            print("\n" + "=" * 80)
            print("DATA INTEGRITY VALIDATION")
            print("=" * 80)

            if issues:
                print(f"\n⚠️  Found {len(issues)} integrity issues:\n")
                for issue in issues:
                    print(f"  {issue}")
                sys.exit(1)
            else:
                print("\n✅ All integrity checks passed!")

                # Print statistics
                total_shifts = await db.execute(select(func.count(Shift.id)))
                total_templates = await db.execute(select(func.count(ShiftTemplate.id)))
                total_assignments = await db.execute(select(func.count(ShiftAssignment.id)))
                total_transfers = await db.execute(select(func.count(ShiftTransfer.id)))

                print("\nStatistics:")
                print(f"  Shifts: {total_shifts.scalar()}")
                print(f"  Templates: {total_templates.scalar()}")
                print(f"  Assignments: {total_assignments.scalar()}")
                print(f"  Transfers: {total_transfers.scalar()}")

                sys.exit(0)

    except Exception as e:
        logger.error(f"Integrity validation failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Shift Service Migration Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate migration data
  python cli/migrate.py validate --source-db postgresql://user:pass@host/db

  # Execute migration
  python cli/migrate.py migrate --source-db postgresql://user:pass@host/db

  # Rollback migration
  python cli/migrate.py rollback --rollback-file rollback_shifts_migration_20251002_120000.json

  # Check database schema
  python cli/migrate.py check-schema

  # Validate data integrity
  python cli/migrate.py validate-integrity
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate migration data')
    validate_parser.add_argument('--source-db', required=True, help='Source database connection string')

    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Execute migration')
    migrate_parser.add_argument('--source-db', required=True, help='Source database connection string')
    migrate_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')

    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback migration')
    rollback_parser.add_argument('--rollback-file', required=True, help='Path to rollback data file')
    rollback_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')

    # Check schema command
    subparsers.add_parser('check-schema', help='Check database schema status')

    # Validate integrity command
    subparsers.add_parser('validate-integrity', help='Validate data integrity')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run appropriate command
    command_map = {
        'validate': cmd_validate,
        'migrate': cmd_migrate,
        'rollback': cmd_rollback,
        'check-schema': cmd_check_schema,
        'validate-integrity': cmd_validate_integrity
    }

    asyncio.run(command_map[args.command](args))


if __name__ == "__main__":
    main()
