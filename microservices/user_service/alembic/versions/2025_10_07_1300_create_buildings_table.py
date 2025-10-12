"""Create buildings table for Building Directory

Revision ID: 001_buildings
Revises:
Create Date: 2025-10-07 13:00:00.000000

Task 1.1: Create Buildings Table Migration (P0)
Week 1, Day 1 - Building Directory Implementation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_buildings'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create buildings table with all required fields and indexes."""

    # Create buildings table
    op.create_table(
        'buildings',

        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Tenant isolation
        sa.Column('management_company_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),

        # Address components (required)
        sa.Column('city', sa.String(100), nullable=False, index=True),
        sa.Column('street', sa.String(200), nullable=False, index=True),
        sa.Column('house_number', sa.String(20), nullable=False),

        # Address components (optional)
        sa.Column('district', sa.String(100), nullable=True),
        sa.Column('building_corpus', sa.String(10), nullable=True),
        sa.Column('postal_code', sa.String(10), nullable=True),

        # Geocoding data (nullable, filled by geocoding service)
        sa.Column('latitude', sa.Numeric(10, 8), nullable=True),
        sa.Column('longitude', sa.Numeric(11, 8), nullable=True),
        sa.Column('coordinates_source', sa.String(50), nullable=True),  # 'google_maps', 'manual', 'yandex_maps'
        sa.Column('geocoded_at', sa.DateTime(timezone=True), nullable=True),

        # Building extra data
        sa.Column('building_type', sa.String(50), nullable=True),  # 'residential', 'commercial', 'mixed'
        sa.Column('floors_count', sa.Integer, nullable=True),
        sa.Column('entrance_count', sa.Integer, nullable=True),
        sa.Column('apartments_count', sa.Integer, nullable=True),
        sa.Column('year_built', sa.Integer, nullable=True),

        # Additional information
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('extra_data', postgresql.JSONB, nullable=True),  # Extensible JSON field

        # Audit fields
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),  # User ID
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),  # User ID

        # Soft delete support
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create composite index for unique address per management company
    op.create_index(
        'ix_buildings_unique_address',
        'buildings',
        ['management_company_id', 'city', 'street', 'house_number', 'building_corpus'],
        unique=True,
        postgresql_where=sa.text("is_active = true AND deleted_at IS NULL")
    )

    # Create spatial index for geocoded buildings (GIN index for efficient coordinate lookups)
    op.create_index(
        'ix_buildings_coordinates',
        'buildings',
        ['latitude', 'longitude'],
        postgresql_where=sa.text("latitude IS NOT NULL AND longitude IS NOT NULL")
    )

    # Create index for filtering by tenant
    op.create_index(
        'ix_buildings_mc_active',
        'buildings',
        ['management_company_id', 'is_active']
    )

    # Create GIN index for JSONB extra_data searches
    op.create_index(
        'ix_buildings_extra_data_gin',
        'buildings',
        ['extra_data'],
        postgresql_using='gin'
    )

    # Create index for city-based searches (most common filter)
    op.create_index(
        'ix_buildings_city_street',
        'buildings',
        ['city', 'street']
    )

    # Create partial index for buildings without coordinates (for geocoding queue)
    op.create_index(
        'ix_buildings_needs_geocoding',
        'buildings',
        ['id'],
        postgresql_where=sa.text("latitude IS NULL AND is_active = true")
    )

    # Add trigger for updated_at auto-update
    op.execute("""
        CREATE OR REPLACE FUNCTION update_buildings_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER buildings_updated_at_trigger
        BEFORE UPDATE ON buildings
        FOR EACH ROW
        EXECUTE FUNCTION update_buildings_updated_at();
    """)

    # Add comment to table
    op.execute("""
        COMMENT ON TABLE buildings IS 'Centralized building directory for property management companies';
        COMMENT ON COLUMN buildings.management_company_id IS 'Tenant isolation: which УК owns this building';
        COMMENT ON COLUMN buildings.coordinates_source IS 'Source of geocoding: google_maps, manual, yandex_maps';
        COMMENT ON COLUMN buildings.extra_data IS 'Extensible JSONB field for custom attributes';
    """)


def downgrade() -> None:
    """Drop buildings table and related objects."""

    # Drop trigger first
    op.execute("DROP TRIGGER IF EXISTS buildings_updated_at_trigger ON buildings")
    op.execute("DROP FUNCTION IF EXISTS update_buildings_updated_at()")

    # Drop indexes (will be dropped automatically with table, but explicit for clarity)
    op.drop_index('ix_buildings_needs_geocoding', table_name='buildings')
    op.drop_index('ix_buildings_city_street', table_name='buildings')
    op.drop_index('ix_buildings_extra_data_gin', table_name='buildings')
    op.drop_index('ix_buildings_mc_active', table_name='buildings')
    op.drop_index('ix_buildings_coordinates', table_name='buildings')
    op.drop_index('ix_buildings_unique_address', table_name='buildings')

    # Drop table
    op.drop_table('buildings')
