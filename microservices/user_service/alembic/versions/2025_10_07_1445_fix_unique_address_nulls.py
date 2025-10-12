"""fix unique address index to treat nulls as equal

Revision ID: 2025_10_07_1445
Revises: 2025_10_07_1300
Create Date: 2025-10-07 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2025_10_07_1445'
down_revision: Union[str, None] = '2025_10_07_1300'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database: recreate unique index with NULLS NOT DISTINCT."""
    # Drop the old unique index
    op.drop_index('ix_buildings_unique_address', table_name='buildings')

    # Recreate with NULLS NOT DISTINCT
    op.execute("""
        CREATE UNIQUE INDEX ix_buildings_unique_address
        ON buildings (management_company_id, city, street, house_number, building_corpus)
        NULLS NOT DISTINCT
        WHERE is_active = true AND deleted_at IS NULL
    """)


def downgrade() -> None:
    """Downgrade database: recreate old unique index without NULLS NOT DISTINCT."""
    # Drop the new index
    op.drop_index('ix_buildings_unique_address', table_name='buildings')

    # Recreate old version (treats NULLs as distinct)
    op.execute("""
        CREATE UNIQUE INDEX ix_buildings_unique_address
        ON buildings (management_company_id, city, street, house_number, building_corpus)
        WHERE is_active = true AND deleted_at IS NULL
    """)
