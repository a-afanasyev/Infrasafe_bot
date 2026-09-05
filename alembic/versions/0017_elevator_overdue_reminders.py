"""Модуль «Лифты» (Ф6): метки еженедельных напоминаний после истечения договора
и освидетельствования.

``elevators.contract_reminder_stage`` / ``cert_reminder_stage`` хранят стадии
ДО срока (30/14/7 дней); после истечения напоминание повторяется еженедельно,
и для этого нужна отдельная метка «когда слали последний раз» — по образцу
``downtime_reminded_at`` (простой) и
``elevator_maintenance_occurrences.overdue_reminded_at`` (просрочка ТО).
Обе колонки nullable timestamptz: NULL = после истечения ещё не напоминали.
Сброс при смене даты — на стороне сервиса: ``passport.update_passport_*``
(обе колонки) и ``calendar._apply_cert`` (``cert_overdue_reminded_at`` при
закрытии освидетельствования с новыми реквизитами).

Revision ID: 017
Revises: 016
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("contract_overdue_reminded_at", "cert_overdue_reminded_at")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("elevators", sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("elevators", name)
