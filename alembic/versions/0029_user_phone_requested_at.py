"""Когда менеджер последний раз запросил у пользователя номер: ``users.phone_requested_at``.

Надпись «Номер запрошен» в карточках жителя/сотрудника жила только в памяти
браузера и пропадала при обновлении страницы. Штамп ставит успешная доставка
запроса (api/users/phone_request.py). Бэкфилла нет — истории запросов нет.

ADD COLUMN без default — изменение только каталога.

Revision ID: 029
Revises: 028
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "phone_requested_at")
