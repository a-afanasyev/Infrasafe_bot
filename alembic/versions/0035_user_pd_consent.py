"""Согласие на обработку персональных данных: ``users.pd_consent_*``.

``pd_consent_at`` + ``pd_consent_version`` — когда и с какой редакцией текста
пользователь согласился (доказательство согласия хранит оператор: ЗРУ-547,
ст. 31). ``pd_consent_notified_at`` — когда бот показал уведомление уже
зарегистрированному пользователю; следующее его действие засчитывается как
согласие (services/pd_consent.py). Бэкфилла нет: согласие задним числом не
ставится.

ADD COLUMN без default — изменение только каталога.

Revision ID: 035
Revises: 034
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("pd_consent_at", sa.DateTime(timezone=True)),
    ("pd_consent_version", sa.String(20)),
    ("pd_consent_notified_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for name, column_type in _COLUMNS:
        op.add_column("users", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("users", name)
