"""Момент сдачи работы исполнителем: ``requests.executed_at``.

`completed_at` ставится только при «Принято» и включает ожидание проверки и
приёмки. Аналитике исполнителей нужен момент «Выполнена» — его пишет
планировщик на EXECUTOR_COMPLETE/MANAGER_COMPLETE. Бэкфилла нет: история
статусов ненадёжна, у старых заявок поле пустое.

ADD COLUMN без default — изменение только каталога.

Revision ID: 025
Revises: 024
Create Date: 2026-10-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requests",
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("requests", "executed_at")
