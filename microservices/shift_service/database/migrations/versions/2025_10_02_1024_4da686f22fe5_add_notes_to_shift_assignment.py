"""add_notes_to_shift_assignment

Revision ID: 4da686f22fe5
Revises: a4bc28241d88
Create Date: 2025-10-02 10:24:21.759203+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4da686f22fe5"
down_revision: Union[str, None] = "a4bc28241d88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notes column to shift_assignments table
    # Check if column doesn't exist before adding (idempotent)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'shift_assignments' AND column_name = 'notes'
            ) THEN
                ALTER TABLE shift_assignments ADD COLUMN notes TEXT;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove notes column from shift_assignments table
    op.execute("ALTER TABLE shift_assignments DROP COLUMN IF EXISTS notes;")
