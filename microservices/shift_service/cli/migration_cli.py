#!/usr/bin/env python3
# Migration CLI for Shift Service
# UK Management Bot - Shift Service

import asyncio
import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.migration_utils import (
    validate_migration_data,
    execute_migration,
    rollback_migration,
    DataMigrationService
)
from database import init_database


async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Shift Service Data Migration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate migration data
  python migration_cli.py validate --source "postgresql://user:pass@host:5432/monolith_db"

  # Execute migration
  python migration_cli.py migrate --source "postgresql://user:pass@host:5432/monolith_db"

  # Rollback migration
  python migration_cli.py rollback --file "rollback_shifts_migration_20231201_120000.json"

  # Check migration status
  python migration_cli.py status
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate migration data without executing migration"
    )
    validate_parser.add_argument(
        "--source",
        required=True,
        help="Source database connection string"
    )
    validate_parser.add_argument(
        "--output",
        help="Output file for validation report (JSON)"
    )

    # Migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Execute data migration from monolith"
    )
    migrate_parser.add_argument(
        "--source",
        required=True,
        help="Source database connection string"
    )
    migrate_parser.add_argument(
        "--output",
        help="Output file for migration report (JSON)"
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run (validation only)"
    )

    # Rollback command
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Rollback migration using rollback file"
    )
    rollback_parser.add_argument(
        "--file",
        required=True,
        help="Rollback data file path"
    )
    rollback_parser.add_argument(
        "--output",
        help="Output file for rollback report (JSON)"
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Check migration status and statistics"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize database
    init_database()

    try:
        if args.command == "validate":
            await handle_validate(args)
        elif args.command == "migrate":
            await handle_migrate(args)
        elif args.command == "rollback":
            await handle_rollback(args)
        elif args.command == "status":
            await handle_status(args)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


async def handle_validate(args):
    """Handle validate command"""
    print("🔍 Validating migration data...")

    report = await validate_migration_data(args.source)

    # Print summary
    print_validation_summary(report)

    # Save report if requested
    if args.output:
        save_report(report, args.output)
        print(f"📁 Validation report saved to {args.output}")


async def handle_migrate(args):
    """Handle migrate command"""
    if args.dry_run:
        print("🔍 Performing dry run migration...")
        report = await validate_migration_data(args.source)
        print_validation_summary(report)
    else:
        print("🚀 Starting data migration...")
        print("⚠️  This will modify the database. Press Ctrl+C to cancel.")

        # Ask for confirmation
        try:
            input("Press Enter to continue or Ctrl+C to cancel...")
        except KeyboardInterrupt:
            print("\n❌ Migration cancelled by user")
            return

        report = await execute_migration(args.source)
        print_migration_summary(report)

    # Save report if requested
    if args.output:
        save_report(report, args.output)
        print(f"📁 Migration report saved to {args.output}")


async def handle_rollback(args):
    """Handle rollback command"""
    print(f"🔄 Starting migration rollback from {args.file}...")
    print("⚠️  This will delete migrated data. Press Ctrl+C to cancel.")

    # Ask for confirmation
    try:
        input("Press Enter to continue or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\n❌ Rollback cancelled by user")
        return

    report = await rollback_migration(args.file)
    print_rollback_summary(report)

    # Save report if requested
    if args.output:
        save_report(report, args.output)
        print(f"📁 Rollback report saved to {args.output}")


async def handle_status(args):
    """Handle status command"""
    print("📊 Checking migration status...")

    try:
        from database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            # Get basic statistics
            result = await db.execute(text("SELECT COUNT(*) FROM shifts"))
            shift_count = result.scalar()

            result = await db.execute(text("SELECT COUNT(*) FROM shift_templates"))
            template_count = result.scalar()

            result = await db.execute(text("SELECT COUNT(*) FROM shift_assignments"))
            assignment_count = result.scalar()

            print(f"📈 Current Statistics:")
            print(f"   • Shifts: {shift_count:,}")
            print(f"   • Templates: {template_count:,}")
            print(f"   • Assignments: {assignment_count:,}")

            # Check recent activity
            result = await db.execute(text("""
                SELECT COUNT(*) FROM shifts
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """))
            recent_shifts = result.scalar()

            print(f"📅 Recent Activity (24h):")
            print(f"   • New shifts: {recent_shifts:,}")

    except Exception as e:
        print(f"❌ Failed to get status: {e}")


def print_validation_summary(report):
    """Print validation summary"""
    print(f"\n📊 Validation Summary:")
    print(f"   • Total records: {report['total_records']:,}")
    print(f"   • Validation mode: {report['validation_mode']}")

    if report['errors']:
        print(f"   • ❌ Errors found: {len(report['errors'])}")
        print("\n🚨 Validation Errors:")
        for error in report['errors'][:10]:  # Show first 10 errors
            print(f"     • {error}")
        if len(report['errors']) > 10:
            print(f"     • ... and {len(report['errors']) - 10} more errors")
    else:
        print(f"   • ✅ No validation errors found")


def print_migration_summary(report):
    """Print migration summary"""
    print(f"\n📊 Migration Summary:")
    print(f"   • Total records: {report['total_records']:,}")
    print(f"   • Migrated records: {report['migrated_records']:,}")
    print(f"   • Failed records: {report['failed_records']:,}")

    if report['rollback_data_file']:
        print(f"   • 🔄 Rollback file: {report['rollback_data_file']}")

    if report['errors']:
        print(f"   • ❌ Errors: {len(report['errors'])}")
    else:
        print(f"   • ✅ Migration completed successfully")

    print(f"   • ⏱️  Duration: {report['started_at']} to {report['completed_at']}")


def print_rollback_summary(report):
    """Print rollback summary"""
    print(f"\n📊 Rollback Summary:")
    print(f"   • Records processed: {report['records_processed']:,}")
    print(f"   • Records deleted: {report['records_deleted']:,}")

    if report['errors']:
        print(f"   • ❌ Errors: {len(report['errors'])}")
        for error in report['errors']:
            print(f"     • {error}")
    else:
        print(f"   • ✅ Rollback completed successfully")

    print(f"   • ⏱️  Duration: {report['started_at']} to {report['completed_at']}")


def save_report(report, filename):
    """Save report to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
    except Exception as e:
        print(f"❌ Failed to save report: {e}")


if __name__ == "__main__":
    asyncio.run(main())