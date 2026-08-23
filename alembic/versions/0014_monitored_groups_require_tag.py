"""Group Intake: тег-режим группы (require_tag).

Решение владельца 2026-08-23: группа с ``require_tag=true`` обрабатывает
ТОЛЬКО сообщения с тегом ``#заявка``/``#ariza`` — остальное не уходит в LLM
вовсе (приватность, стоимость, ноль ложных срабатываний). Дефолт false:
жительские группы продолжают авто-отлов, поведение существующих строк не
меняется. Включается менеджером per-group из дашборда «Группы».

Идемпотентность управляется alembic-версией; отдельных guard'ов не требуется.

Revision ID: 014
Revises: 013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitored_groups",
        sa.Column(
            "require_tag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("monitored_groups", "require_tag")
