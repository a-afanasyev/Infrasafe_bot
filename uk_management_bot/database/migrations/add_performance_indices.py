"""
Migration: add performance indices.

Adds indices for frequently queried columns:
- requests.status (filter by status)
- requests.created_at (sort by date)
- users.status (filter active users)
- audit_logs.action (filter by action type)
- shifts.user_id + shifts.status (composite: active shifts per user)

Date: 2026-03-08
"""
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def upgrade(engine):
    """Apply migration - create performance indices."""
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            logger.info("Starting migration: add performance indices")

            indices = [
                ("ix_requests_status", "requests", "status"),
                ("ix_requests_created_at", "requests", "created_at"),
                ("ix_users_status", "users", "status"),
                ("ix_audit_logs_action", "audit_logs", "action"),
            ]

            for idx_name, table, column in indices:
                try:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"
                    ))
                    logger.info(f"Created index {idx_name} on {table}.{column}")
                except Exception as e:
                    logger.warning(f"Index {idx_name} may already exist: {e}")

            # Composite index for shifts
            try:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_shifts_user_status "
                    "ON shifts (user_id, status)"
                ))
                logger.info("Created composite index ix_shifts_user_status")
            except Exception as e:
                logger.warning(f"Composite index may already exist: {e}")

            transaction.commit()
            logger.info("Migration completed: performance indices added")

        except Exception as e:
            transaction.rollback()
            logger.error(f"Migration failed: {e}")
            raise


def downgrade(engine):
    """Revert migration - drop performance indices."""
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            for idx_name in [
                "ix_requests_status",
                "ix_requests_created_at",
                "ix_users_status",
                "ix_audit_logs_action",
                "ix_shifts_user_status",
            ]:
                try:
                    conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
                except Exception as e:
                    logger.warning(f"Could not drop index {idx_name}: {e}")

            transaction.commit()
            logger.info("Migration reverted: performance indices removed")

        except Exception as e:
            transaction.rollback()
            logger.error(f"Downgrade failed: {e}")
            raise
