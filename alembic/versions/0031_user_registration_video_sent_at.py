"""Когда жителю последний раз отправили видео о регистрации: ``users.registration_video_sent_at``.

Кнопка «🎬 Видео о регистрации» в карточке жителя, бросившего регистрацию,
шлёт ролик не чаще раза в сутки (api/residents/registration_video.py). Штамп
ставит успешная доставка. Бэкфилла нет.

ADD COLUMN без default — изменение только каталога.

Revision ID: 031
Revises: 030
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("registration_video_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "registration_video_sent_at")
