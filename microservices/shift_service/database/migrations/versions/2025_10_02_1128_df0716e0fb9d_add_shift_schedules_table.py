"""add_shift_schedules_table

Revision ID: df0716e0fb9d
Revises: 5e8a9b2c1f3d
Create Date: 2025-10-02 11:28:52.530477+00:00

Add ShiftSchedule model for daily shift planning and coverage tracking
Migrated from monolith: uk_management_bot/database/models/shift_schedule.py
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "df0716e0fb9d"
down_revision: Union[str, None] = "5e8a9b2c1f3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create shift_schedules table"""
    op.create_table(
        'shift_schedules',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),

        # Core fields
        sa.Column('date', sa.Date(), nullable=False, unique=True, index=True),

        # Coverage planning
        sa.Column('planned_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment="Planned hourly coverage: {'09:00': 2, '10:00': 3}"),
        sa.Column('actual_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment="Actual hourly coverage: {'09:00': 2, '10:00': 3}"),
        sa.Column('planned_specialization_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment="Planned specialization coverage: {'PLUMBER': 2, 'ELECTRICIAN': 1}"),
        sa.Column('actual_specialization_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment="Actual specialization coverage: {'PLUMBER': 2, 'ELECTRICIAN': 1}"),

        # Predictions
        sa.Column('predicted_requests', sa.Integer(), nullable=True, comment="Predicted request count"),
        sa.Column('actual_requests', sa.Integer(), nullable=False, server_default='0', comment="Actual request count"),
        sa.Column('prediction_accuracy', sa.Float(), nullable=True, comment="Prediction accuracy percentage (0.0-100.0)"),
        sa.Column('recommended_shifts', sa.Integer(), nullable=True, comment="AI-recommended shift count"),
        sa.Column('actual_shifts', sa.Integer(), nullable=False, server_default='0', comment="Actual created shift count"),

        # Optimization metrics
        sa.Column('optimization_score', sa.Float(), nullable=True, comment="Schedule optimization score (0.0-100.0)"),
        sa.Column('coverage_percentage', sa.Float(), nullable=True, comment="Coverage fulfillment percentage (0.0-100.0)"),
        sa.Column('load_balance_score', sa.Float(), nullable=True, comment="Load balance score across executors (0.0-100.0)"),

        # Additional info
        sa.Column('special_conditions', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment="Special day conditions: ['holiday', 'event', 'maintenance']"),
        sa.Column('manual_adjustments', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment="Manager manual adjustments"),
        sa.Column('notes', sa.String(500), nullable=True, comment="Schedule notes"),

        # Status and metadata
        sa.Column('status', sa.String(50), nullable=False, server_default='draft', index=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True, comment="User service reference"),
        sa.Column('auto_generated', sa.Boolean(), nullable=False, server_default='false', comment="AI auto-generated flag"),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1', comment="Schedule version number"),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),

        # Constraints
        sa.CheckConstraint('predicted_requests >= 0', name='positive_predicted_requests'),
        sa.CheckConstraint('actual_requests >= 0', name='positive_actual_requests'),
        sa.CheckConstraint('recommended_shifts >= 0', name='positive_recommended_shifts'),
        sa.CheckConstraint('actual_shifts >= 0', name='positive_actual_shifts'),
        sa.CheckConstraint(
            'prediction_accuracy IS NULL OR (prediction_accuracy >= 0.0 AND prediction_accuracy <= 100.0)',
            name='valid_prediction_accuracy'
        ),
        sa.CheckConstraint(
            'optimization_score IS NULL OR (optimization_score >= 0.0 AND optimization_score <= 100.0)',
            name='valid_optimization_score'
        ),
        sa.CheckConstraint(
            'coverage_percentage IS NULL OR (coverage_percentage >= 0.0 AND coverage_percentage <= 100.0)',
            name='valid_coverage_percentage'
        ),
        sa.CheckConstraint(
            'load_balance_score IS NULL OR (load_balance_score >= 0.0 AND load_balance_score <= 100.0)',
            name='valid_load_balance_score'
        ),
    )

    # Create composite indexes
    op.create_index('idx_shift_schedules_date_status', 'shift_schedules', ['date', 'status'])
    op.create_index('idx_shift_schedules_created_by', 'shift_schedules', ['created_by'])


def downgrade() -> None:
    """Drop shift_schedules table"""
    op.drop_index('idx_shift_schedules_created_by', table_name='shift_schedules')
    op.drop_index('idx_shift_schedules_date_status', table_name='shift_schedules')
    op.drop_table('shift_schedules')
