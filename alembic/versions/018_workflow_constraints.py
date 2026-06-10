"""Constraints-фаза SSOT-кластера #1 (план, staged-rollout шаг 0; PR0 Р8)

DB-гарантии идемпотентности workflow ДО включения mutation-layer (PR2):
  1. `ratings`: UNIQUE(request_number) — одна оценка на заявку (повторный
     APPLICANT_ACCEPT не создаст дубль даже при гонке).
  2. `request_assignments`: partial-unique НА АКТИВНОЕ назначение
     (WHERE status='active') — история cancelled/completed сохраняется,
     unique-по-заявке уничтожил бы её (риск №44 плана).

Remediation existing-данных ПЕРЕД constraints (на проде 2026-06-10 дублей
нет — preflight чист; код обязан быть безопасным на любой БД):
  - дубли ratings: остаётся новейшая (max id);
  - несколько active-назначений: новейшее остаётся active, прочие → cancelled.

ИДЕМПОТЕНТНО: CI/локальный бутстрап = create_all + stamp + upgrade head —
после create_all constraint/index уже существуют (объявлены в моделях);
создаём только при отсутствии. Remediation — повторно-безопасные запросы.

Revision ID: 018
Revises: 017
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RATINGS_UQ = "uq_ratings_request_number"
ASSIGN_UQ_IDX = "uq_request_assignments_active"

# Дубли оценок: оставить новейшую (max id) на заявку
DEDUPE_RATINGS_SQL = """
DELETE FROM ratings r
USING ratings newer
WHERE r.request_number = newer.request_number
  AND r.id < newer.id
"""

# Несколько активных назначений: новейшее остаётся, прочие → cancelled
DEDUPE_ASSIGNMENTS_SQL = """
UPDATE request_assignments ra
SET status = 'cancelled'
WHERE ra.status = 'active'
  AND EXISTS (
        SELECT 1 FROM request_assignments newer
        WHERE newer.request_number = ra.request_number
          AND newer.status = 'active'
          AND newer.id > ra.id
  )
"""


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "ratings" in tables:
        if conn.dialect.name == "postgresql":
            op.execute(DEDUPE_RATINGS_SQL)
        uqs = {u["name"] for u in insp.get_unique_constraints("ratings")}
        # create_all-база уже несёт constraint из модели
        if RATINGS_UQ not in uqs:
            op.create_unique_constraint(RATINGS_UQ, "ratings", ["request_number"])

    if "request_assignments" in tables:
        if conn.dialect.name == "postgresql":
            op.execute(DEDUPE_ASSIGNMENTS_SQL)
        idx = {i["name"] for i in insp.get_indexes("request_assignments")}
        if ASSIGN_UQ_IDX not in idx:
            op.create_index(
                ASSIGN_UQ_IDX, "request_assignments", ["request_number"],
                unique=True,
                postgresql_where=sa.text("status = 'active'"),
                sqlite_where=sa.text("status = 'active'"),
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "request_assignments" in tables:
        idx = {i["name"] for i in insp.get_indexes("request_assignments")}
        if ASSIGN_UQ_IDX in idx:
            op.drop_index(ASSIGN_UQ_IDX, table_name="request_assignments")
    if "ratings" in tables:
        uqs = {u["name"] for u in insp.get_unique_constraints("ratings")}
        if RATINGS_UQ in uqs:
            op.drop_constraint(RATINGS_UQ, "ratings", type_="unique")
