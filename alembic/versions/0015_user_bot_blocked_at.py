"""Статус «бот заблокирован» в карточках жителей/сотрудников.

Прод-случай 2026-09-01: менеджер жал «Запросить номер» жителям, заблокировавшим
бота, и до фикса вердиктов не понимал причину отказа. Теперь факт блокировки
хранится штампом ``users.bot_blocked_at`` и показывается бейджем в карточке.
Пишут его два источника: realtime ``my_chat_member`` (kicked → set, member →
clear) и вердикт доставки запроса номера. NULL = не заблокирован.

Идемпотентность управляется alembic-версией; отдельных guard'ов не требуется.

Revision ID: 015
Revises: 014
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("bot_blocked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "bot_blocked_at")
