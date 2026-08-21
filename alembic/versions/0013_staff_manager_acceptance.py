"""Group Intake фаза 2: staff-репорты с менеджерской приёмкой.

Две колонки на ``requests`` (решение владельца 2026-08-22, модель №1):

1. ``reported_by_user_id`` — сотрудник-автор staff-репорта (FK users,
   ON DELETE SET NULL: увольнение сотрудника не трогает заявку). Провенанс
   «кто доложил» отдельно от владельца ``user_id`` — переживёт возможное
   будущее перевешивание владельца. NULL для всех остальных путей создания.

2. ``acceptance_mode`` — кто принимает результат: ``resident`` (дефолт,
   весь существующий поток: подтверждение менеджера → приёмка/оценка
   жителем) | ``manager`` (staff-репорт: подтверждение менеджера сразу
   завершает заявку «Принято», жительского шага нет). server_default
   закрывает все существующие строки как resident — поведение не меняется.

Идемпотентность управляется alembic-версией; отдельных guard'ов не требуется.

Revision ID: 013
Revises: 012
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requests",
        sa.Column(
            "reported_by_user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_requests_reported_by_user_id_users",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "requests",
        sa.Column(
            "acceptance_mode",
            sa.String(length=20),
            nullable=False,
            server_default="resident",
        ),
    )
    op.create_check_constraint(
        "ck_requests_acceptance_mode",
        "requests",
        "acceptance_mode IN ('resident', 'manager')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_requests_acceptance_mode", "requests", type_="check"
    )
    op.drop_column("requests", "acceptance_mode")
    op.drop_column("requests", "reported_by_user_id")
