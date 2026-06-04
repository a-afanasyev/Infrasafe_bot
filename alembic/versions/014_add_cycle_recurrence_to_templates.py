"""add cycle recurrence columns to shift_templates

Добавляет режим повторения «цикл N/M» к шаблонам смен: новый режим
``recurrence_mode`` ("weekday" | "cycle") плюс параметры цикла
``cycle_days_on`` / ``cycle_days_off`` / ``cycle_anchor_date``.

Двойной guard (важно — ``shift_templates`` НЕ создаётся alembic-цепочкой):
таблица появляется через ORM ``Base.metadata.create_all`` или внецепочный
``add_advanced_shift_features.py``, не через миграцию. Бутстрап проекта =
``create_all`` + ``stamp`` + ``upgrade head``, поэтому к моменту 014 таблица
уже есть — но из ``create_all`` она придёт уже с новыми колонками (модель их
определяет). Значит миграция должна:
1. если таблицы ``shift_templates`` нет → no-op (её создаст ``create_all``);
2. иначе для каждой колонки ``add_column`` только если колонки ещё нет
   (иначе на create_all-базе будет duplicate-column).

Revision ID: 014
Revises: 013
Create Date: 2026-06-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _new_columns() -> list:
    # Свежие Column-объекты на каждый вызов (Column нельзя переиспользовать в SA 2.0).
    return [
        sa.Column("recurrence_mode", sa.String(20), nullable=False, server_default="weekday"),
        sa.Column("cycle_days_on", sa.Integer(), nullable=True),
        sa.Column("cycle_days_off", sa.Integer(), nullable=True),
        sa.Column("cycle_anchor_date", sa.Date(), nullable=True),
    ]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "shift_templates" not in insp.get_table_names():
        return  # no-op: таблицу создаст create_all уже с колонками
    existing = {c["name"] for c in insp.get_columns("shift_templates")}
    for col in _new_columns():
        if col.name not in existing:
            op.add_column("shift_templates", col)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "shift_templates" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("shift_templates")}
    for name in ("cycle_anchor_date", "cycle_days_off", "cycle_days_on", "recurrence_mode"):
        if name in existing:
            op.drop_column("shift_templates", name)
