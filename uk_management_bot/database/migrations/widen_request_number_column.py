"""
Migration: widen request_number columns from String(10) to String(15)
Prevents truncation when >999 requests/day (YYMMDD-NNNN = 11 chars)

Affected tables (PK + 5 FKs):
  - requests.request_number (PK)
  - request_comments.request_number (FK)
  - request_assignments.request_number (FK)
  - shift_assignments.request_number (FK)
  - ratings.request_number (FK)
  - notifications.request_number_fk (FK)

PostgreSQL ALTER COLUMN TYPE VARCHAR(15) is metadata-only when widening — no table rewrite.
"""

import logging
from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

revision = 'widen_request_number_001'
down_revision = None
branch_labels = None
depends_on = None

# All (table, column) pairs that store request_number
_COLUMNS = [
    ("requests", "request_number"),
    ("request_comments", "request_number"),
    ("request_assignments", "request_number"),
    ("shift_assignments", "request_number"),
    ("ratings", "request_number"),
    ("notifications", "request_number_fk"),
]


def upgrade():
    logger.info("Widening request_number columns to VARCHAR(15)")
    for table, column in _COLUMNS:
        try:
            op.alter_column(
                table,
                column,
                type_=sa.String(15),
                existing_type=sa.String(10),
            )
            logger.info(f"  OK: {table}.{column}")
        except Exception as e:
            logger.warning(f"  SKIP {table}.{column}: {e}")


def downgrade():
    logger.info("Reverting request_number columns to VARCHAR(10)")
    for table, column in _COLUMNS:
        try:
            op.alter_column(
                table,
                column,
                type_=sa.String(10),
                existing_type=sa.String(15),
            )
        except Exception as e:
            logger.warning(f"  SKIP {table}.{column}: {e}")
