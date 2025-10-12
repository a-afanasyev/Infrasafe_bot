"""Update building_id to UUID and add building_address

Revision ID: 001_building_integration
Revises:
Create Date: 2025-10-07 14:00:00.000000

Task 9.1: Update Request Models & Migrations (P0)
Week 3, Day 1 - Building Directory Integration
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_building_integration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Update building fields for Building Directory integration.

    Changes:
    1. Change building_id from String to UUID
    2. Add building_address for denormalized address from Directory
    3. Keep address field for user details (apartment/entrance/floor)
    """

    # Step 1: Drop old building_id column (if data exists, this should be done carefully in production)
    # In production, you would first migrate data, then drop
    op.drop_column('requests', 'building_id')

    # Step 2: Add new building_id as UUID (nullable for existing data)
    op.add_column(
        'requests',
        sa.Column('building_id', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Step 3: Add building_address for denormalized full address from Directory
    op.add_column(
        'requests',
        sa.Column('building_address', sa.String(500), nullable=True,
                  comment='Denormalized full address from Building Directory')
    )

    # ⚠️ ВАЖНО: address колонка ОСТАЕТСЯ БЕЗ ИЗМЕНЕНИЙ
    # Согласно архитектурному плану (UNIFIED_BUILDING_DIRECTORY.md:415):
    # "address используется как пользовательский ввод для уточнений"
    # Это поле для apartment/entrance/floor - НЕ переименовывать!

    # Step 4: Create index on building_id for faster lookups
    op.create_index(
        'ix_requests_building_id',
        'requests',
        ['building_id']
    )

    # Step 5: Create composite index for common query pattern (status + building_id)
    op.create_index(
        'ix_requests_status_building',
        'requests',
        ['status', 'building_id']
    )

    # Step 6: Add comments for documentation
    op.execute("""
        COMMENT ON COLUMN requests.building_id IS 'UUID reference to Building Directory (user-service)';
        COMMENT ON COLUMN requests.building_address IS 'Denormalized full address from Building Directory for performance';
        COMMENT ON COLUMN requests.address IS 'User-provided details: apartment, entrance, floor, etc.';
    """)


def downgrade() -> None:
    """Revert building field changes."""

    # Drop indexes
    op.drop_index('ix_requests_status_building', table_name='requests')
    op.drop_index('ix_requests_building_id', table_name='requests')

    # Remove new columns
    op.drop_column('requests', 'building_address')
    op.drop_column('requests', 'building_id')

    # Restore old building_id as String
    op.add_column(
        'requests',
        sa.Column('building_id', sa.String(50), nullable=True)
    )
