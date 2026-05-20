"""set ON DELETE SET NULL on requests.apartment_id FK (FIX-003)

Purge yard/building падал на FK violation, потому что
`requests.apartment_id -> apartments.id` имела действие ON DELETE NO ACTION.

Миграция: DROP CONSTRAINT + ADD CONSTRAINT с `ondelete='SET NULL'`.
Столбец `requests.apartment_id` уже nullable, дополнительный ALTER не нужен.

Revision ID: 007
Revises: 006
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Имя FK подтверждено через pg_constraint:
#   conname = 'requests_apartment_id_fkey'
CONSTRAINT_NAME = 'requests_apartment_id_fkey'
SOURCE_TABLE = 'requests'
TARGET_TABLE = 'apartments'
LOCAL_COL = 'apartment_id'
REMOTE_COL = 'id'


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, SOURCE_TABLE, type_='foreignkey')
    op.create_foreign_key(
        CONSTRAINT_NAME,
        SOURCE_TABLE,
        TARGET_TABLE,
        [LOCAL_COL],
        [REMOTE_COL],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, SOURCE_TABLE, type_='foreignkey')
    op.create_foreign_key(
        CONSTRAINT_NAME,
        SOURCE_TABLE,
        TARGET_TABLE,
        [LOCAL_COL],
        [REMOTE_COL],
        # No ondelete clause = NO ACTION (original behaviour).
    )
