"""Удаление мёртвых таблиц квартального планирования (AUD6-P2-31).

ORM-модели QuarterlyPlan / QuarterlyShiftSchedule / PlanningConflict удалены
из кода (единственных потребителей у них не было — модуль импортировался
только в database/models/__init__.py), но baseline 0001 создавал три таблицы
на проде. Без drop'а CI-гейт `alembic check` упадёт на дрейфе
metadata ↔ схема.

Порядок drop — сначала зависимые (FK на quarterly_plans.id):
quarterly_shift_schedules и planning_conflicts, затем quarterly_plans.

downgrade честный (гейт b0): восстанавливает все три таблицы ровно по
определениям из baseline 0001 (индексов у этих таблиц в baseline не было).

Revision ID: 008
Revises: 007
Create Date: 2026-07-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('quarterly_shift_schedules')
    op.drop_table('planning_conflicts')
    op.drop_table('quarterly_plans')


def downgrade() -> None:
    # Определения скопированы из 0001_prc05_initial_baseline.py:321,592,614.
    op.create_table('quarterly_plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('quarter', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('specializations', sa.JSON(), nullable=True),
    sa.Column('coverage_24_7', sa.Boolean(), nullable=False),
    sa.Column('load_balancing_enabled', sa.Boolean(), nullable=False),
    sa.Column('auto_transfers_enabled', sa.Boolean(), nullable=False),
    sa.Column('notifications_enabled', sa.Boolean(), nullable=False),
    sa.Column('total_shifts_planned', sa.Integer(), nullable=False),
    sa.Column('total_hours_planned', sa.Float(), nullable=False),
    sa.Column('coverage_percentage', sa.Float(), nullable=False),
    sa.Column('total_conflicts', sa.Integer(), nullable=False),
    sa.Column('resolved_conflicts', sa.Integer(), nullable=False),
    sa.Column('pending_conflicts', sa.Integer(), nullable=False),
    sa.Column('settings', sa.JSON(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('planning_conflicts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quarterly_plan_id', sa.Integer(), nullable=False),
    sa.Column('conflict_type', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('involved_schedule_ids', sa.JSON(), nullable=True),
    sa.Column('involved_user_ids', sa.JSON(), nullable=True),
    sa.Column('conflict_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('conflict_date', sa.Date(), nullable=True),
    sa.Column('conflict_details', sa.JSON(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('suggested_resolutions', sa.JSON(), nullable=True),
    sa.Column('applied_resolution', sa.JSON(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by', sa.Integer(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['quarterly_plan_id'], ['quarterly_plans.id'], ),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('quarterly_shift_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quarterly_plan_id', sa.Integer(), nullable=False),
    sa.Column('planned_date', sa.Date(), nullable=False),
    sa.Column('planned_start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('planned_end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('assigned_user_id', sa.Integer(), nullable=True),
    sa.Column('specialization', sa.String(length=100), nullable=False),
    sa.Column('schedule_type', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('actual_shift_id', sa.Integer(), nullable=True),
    sa.Column('shift_config', sa.JSON(), nullable=True),
    sa.Column('coverage_areas', sa.JSON(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['actual_shift_id'], ['shifts.id'], ),
    sa.ForeignKeyConstraint(['assigned_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['quarterly_plan_id'], ['quarterly_plans.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
