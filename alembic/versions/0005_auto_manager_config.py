"""Auto-manager: singleton-конфиг «автоматического менеджера» (авто-назначение заявок).

Клон board_config (см. 0001, таблица board_config): одна строка id=1,
data JSON/JSONB с настройками enabled/mode/window/timezone/лимита прогона,
updated_at/updated_by. Схема data не enforce-ится на уровне БД — валидацию
несёт сервисный слой (следующая задача). Строка-seed здесь не создаётся:
приложение при отсутствии строки должно падать на дефолты.

Revision ID: 005
Revises: 004
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auto_manager_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auto_manager_config_updated_by"),
        "auto_manager_config",
        ["updated_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auto_manager_config_updated_by"), table_name="auto_manager_config")
    op.drop_table("auto_manager_config")
