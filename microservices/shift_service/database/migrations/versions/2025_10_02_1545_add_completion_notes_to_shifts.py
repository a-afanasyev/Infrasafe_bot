"""Add completion_notes to shifts

Revision ID: 5e8a9b2c1f3d
Revises: 4da686f22fe5
Create Date: 2025-10-02 15:45:00

Bug #18 Fix: Add completion_notes field to Shift model to store notes
when completing a shift. Previously notes parameter was silently ignored.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5e8a9b2c1f3d'
down_revision = '4da686f22fe5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add completion_notes column to shifts table"""
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'shifts' AND column_name = 'completion_notes'
            ) THEN
                ALTER TABLE shifts ADD COLUMN completion_notes TEXT;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove completion_notes column from shifts table"""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'shifts' AND column_name = 'completion_notes'
            ) THEN
                ALTER TABLE shifts DROP COLUMN completion_notes;
            END IF;
        END $$;
    """)
