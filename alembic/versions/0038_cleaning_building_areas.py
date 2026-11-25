"""Площади мест общего пользования дома для нагрузки уборщиц: ``cleaning_building_settings.areas``.

JSON по подъездам (services/cleaning/areas.py): типовой этаж, отличающиеся этажи,
работы-точки. NULL — площади не заданы, нагрузка дома в м² не считается.

ADD COLUMN без default — в PostgreSQL без перезаписи таблицы.

Revision ID: 038
Revises: 037
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cleaning_building_settings", sa.Column(
        "areas", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True))


def downgrade() -> None:
    op.drop_column("cleaning_building_settings", "areas")
