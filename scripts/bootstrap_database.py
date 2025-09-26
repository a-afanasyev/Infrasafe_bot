#!/usr/bin/env python3
"""
Comprehensive Database Bootstrap Script for UK Management Bot

This script creates a clean database structure with all tables using request_number
as the primary key for requests and proper foreign key relationships.

Features:
- Creates all tables from scratch using current models
- Ensures all foreign keys use request_number (not request_id)
- Applies proper indexes for performance
- Validates the final schema
- Can be run on empty or existing databases safely

Usage:
    python scripts/bootstrap_database.py
    python scripts/bootstrap_database.py --clean  # Drop all tables first
    python scripts/bootstrap_database.py --validate-only  # Only validate schema
"""

import argparse
import logging
import sys
import os
from typing import Dict, List, Optional
from sqlalchemy import inspect, text, MetaData, Table, Column, String, Integer
from sqlalchemy.engine import Engine

# Add project root to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    from uk_management_bot.database.session import engine, Base
    from uk_management_bot.config.settings import settings
    from uk_management_bot.database.models import *  # Import all models
except ImportError as e:
    print(f"Error importing project modules: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)

logger = logging.getLogger("bootstrap_db")

def validate_schema(engine: Engine) -> Dict[str, any]:
    """
    Validates that the database schema matches our expectations.

    Returns:
        dict: Validation results with any issues found
    """
    inspector = inspect(engine)
    issues = []
    tables_info = {}

    # Check requests table structure
    if 'requests' in inspector.get_table_names():
        requests_cols = {col['name']: col for col in inspector.get_columns('requests')}
        tables_info['requests'] = requests_cols

        # Validate requests table has request_number as primary key
        pk_constraints = inspector.get_pk_constraint('requests')
        if pk_constraints['constrained_columns'] != ['request_number']:
            issues.append("requests table does not have request_number as primary key")

        # Check that request_number is String type
        if 'request_number' in requests_cols:
            if not isinstance(requests_cols['request_number']['type'], type(String())):
                issues.append("request_number is not String type")
        else:
            issues.append("requests table missing request_number column")
    else:
        issues.append("requests table does not exist")

    # Check foreign key relationships use request_number
    tables_with_request_fks = [
        'request_comments', 'request_assignments', 'shift_assignments'
    ]

    for table_name in tables_with_request_fks:
        if table_name in inspector.get_table_names():
            fks = inspector.get_foreign_keys(table_name)
            for fk in fks:
                if fk['referred_table'] == 'requests':
                    if fk['referred_columns'] != ['request_number']:
                        issues.append(f"{table_name} has FK to requests.{fk['referred_columns']} instead of request_number")
                    if fk['constrained_columns'][0] != 'request_number':
                        issues.append(f"{table_name} FK column should be request_number, not {fk['constrained_columns'][0]}")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'tables': tables_info,
        'table_count': len(inspector.get_table_names())
    }

def drop_all_tables(engine: Engine) -> None:
    """
    Drops all tables in the database.
    """
    logger.info("Dropping all existing tables...")

    with engine.connect() as conn:
        # Get all table names
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        if not table_names:
            logger.info("No tables found to drop")
            return

        # Disable foreign key constraints for dropping
        if engine.name == 'postgresql':
            # For PostgreSQL, drop tables with CASCADE
            for table_name in table_names:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        elif engine.name == 'sqlite':
            # For SQLite, disable foreign keys temporarily
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            for table_name in table_names:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            conn.execute(text("PRAGMA foreign_keys = ON"))
        else:
            # For other databases, try to drop with CASCADE
            for table_name in table_names:
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
                except Exception as e:
                    logger.warning(f"Could not drop {table_name}: {e}")

        conn.commit()
        logger.info(f"Dropped {len(table_names)} tables")

def create_indexes(engine: Engine) -> None:
    """
    Creates additional indexes for performance optimization.
    """
    logger.info("Creating performance indexes...")

    indexes = [
        # Request table indexes
        "CREATE INDEX IF NOT EXISTS idx_requests_date_prefix ON requests (substring(request_number, 1, 6))",
        "CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_requests_executor_id ON requests (executor_id)",
        "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests (status)",
        "CREATE INDEX IF NOT EXISTS idx_requests_category ON requests (category)",
        "CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests (created_at)",

        # Request assignments indexes
        "CREATE INDEX IF NOT EXISTS idx_request_assignments_request_number ON request_assignments (request_number)",
        "CREATE INDEX IF NOT EXISTS idx_request_assignments_executor_id ON request_assignments (executor_id)",
        "CREATE INDEX IF NOT EXISTS idx_request_assignments_status ON request_assignments (status)",

        # Request comments indexes
        "CREATE INDEX IF NOT EXISTS idx_request_comments_request_number ON request_comments (request_number)",
        "CREATE INDEX IF NOT EXISTS idx_request_comments_user_id ON request_comments (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_request_comments_created_at ON request_comments (created_at)",

        # Shift assignments indexes
        "CREATE INDEX IF NOT EXISTS idx_shift_assignments_request_number ON shift_assignments (request_number)",
        "CREATE INDEX IF NOT EXISTS idx_shift_assignments_shift_id ON shift_assignments (shift_id)",
        "CREATE INDEX IF NOT EXISTS idx_shift_assignments_status ON shift_assignments (status)",
    ]

    with engine.connect() as conn:
        for index_sql in indexes:
            try:
                conn.execute(text(index_sql))
                logger.debug(f"Created index: {index_sql.split('idx_')[1].split(' ')[0]}")
            except Exception as e:
                logger.warning(f"Could not create index: {e}")
        conn.commit()

    logger.info("Performance indexes created")

def bootstrap_database(engine: Engine, clean: bool = False) -> Dict[str, any]:
    """
    Creates or updates the database schema to ensure proper request_number usage.

    Args:
        engine: SQLAlchemy engine
        clean: If True, drop all tables first

    Returns:
        dict: Bootstrap results
    """
    result = {
        'cleaned': False,
        'tables_created': 0,
        'indexes_created': False,
        'validation': None
    }

    if clean:
        drop_all_tables(engine)
        result['cleaned'] = True

    # Create all tables from current models
    logger.info("Creating tables from SQLAlchemy models...")
    Base.metadata.create_all(bind=engine)

    # Count created tables
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    result['tables_created'] = len(table_names)
    logger.info(f"Created/verified {len(table_names)} tables")

    # Create performance indexes
    create_indexes(engine)
    result['indexes_created'] = True

    # Validate the final schema
    validation = validate_schema(engine)
    result['validation'] = validation

    if validation['valid']:
        logger.info("✅ Database schema validation passed")
    else:
        logger.error("❌ Database schema validation failed:")
        for issue in validation['issues']:
            logger.error(f"  - {issue}")

    return result

def main():
    parser = argparse.ArgumentParser(description="Bootstrap UK Management Bot database")
    parser.add_argument("--clean", action="store_true",
                       help="Drop all existing tables before creating new ones")
    parser.add_argument("--validate-only", action="store_true",
                       help="Only validate the current schema, don't modify anything")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.info("=== UK Management Bot Database Bootstrap ===")
    logger.info(f"Database URL: {settings.DATABASE_URL}")
    logger.info(f"Engine: {engine.name}")

    try:
        if args.validate_only:
            logger.info("Running schema validation only...")
            validation = validate_schema(engine)

            print(f"\n=== Validation Results ===")
            print(f"Valid: {validation['valid']}")
            print(f"Tables found: {validation['table_count']}")

            if validation['issues']:
                print("\nIssues found:")
                for issue in validation['issues']:
                    print(f"  ❌ {issue}")
            else:
                print("✅ No issues found")

            sys.exit(0 if validation['valid'] else 1)

        # Run full bootstrap
        result = bootstrap_database(engine, clean=args.clean)

        print(f"\n=== Bootstrap Results ===")
        print(f"Tables cleaned: {result['cleaned']}")
        print(f"Tables created/verified: {result['tables_created']}")
        print(f"Indexes created: {result['indexes_created']}")
        print(f"Schema valid: {result['validation']['valid']}")

        if result['validation']['issues']:
            print("\nRemaining issues:")
            for issue in result['validation']['issues']:
                print(f"  ❌ {issue}")
            sys.exit(1)
        else:
            print("✅ Database bootstrap completed successfully")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()