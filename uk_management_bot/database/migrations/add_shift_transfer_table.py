"""
Добавление таблицы для передачи смен между исполнителями

Revision ID: add_shift_transfer_table
Revises: add_materials_fields
Create Date: 2025-09-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_shift_transfer_table'
down_revision = 'add_materials_fields'
branch_labels = None
depends_on = None


def upgrade():
    """Применение миграции - создание таблицы shift_transfers"""

    print("🔄 Создание таблицы shift_transfers...")

    # Создание таблицы shift_transfers
    op.create_table(
        'shift_transfers',

        # Основные поля
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),

        # Связи с другими таблицами
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('from_executor_id', sa.Integer(), nullable=False),
        sa.Column('to_executor_id', sa.Integer(), nullable=True),

        # Статус и причина передачи
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('reason', sa.String(100), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('urgency_level', sa.String(20), nullable=False, server_default='normal'),

        # Временные метки
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),

        # Системная информация
        sa.Column('auto_assigned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),

        # Создание внешних ключей
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_executor_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['to_executor_id'], ['users.id'], ondelete='SET NULL'),

        # Создание первичного ключа
        sa.PrimaryKeyConstraint('id')
    )

    # Создание индексов для оптимизации запросов
    print("🔄 Создание индексов для shift_transfers...")

    op.create_index('idx_shift_transfers_shift_id', 'shift_transfers', ['shift_id'])
    op.create_index('idx_shift_transfers_from_executor', 'shift_transfers', ['from_executor_id'])
    op.create_index('idx_shift_transfers_to_executor', 'shift_transfers', ['to_executor_id'])
    op.create_index('idx_shift_transfers_status', 'shift_transfers', ['status'])
    op.create_index('idx_shift_transfers_reason', 'shift_transfers', ['reason'])
    op.create_index('idx_shift_transfers_created_at', 'shift_transfers', ['created_at'])
    op.create_index('idx_shift_transfers_assigned_at', 'shift_transfers', ['assigned_at'])

    # Создание составных индексов для частых запросов
    op.create_index('idx_shift_transfers_from_status', 'shift_transfers', ['from_executor_id', 'status'])
    op.create_index('idx_shift_transfers_to_status', 'shift_transfers', ['to_executor_id', 'status'])
    op.create_index('idx_shift_transfers_shift_status', 'shift_transfers', ['shift_id', 'status'])

    print("✅ Таблица shift_transfers успешно создана")


def downgrade():
    """Откат миграции - удаление таблицы shift_transfers"""

    print("🔄 Удаление таблицы shift_transfers...")

    # Удаление индексов
    op.drop_index('idx_shift_transfers_shift_status', 'shift_transfers')
    op.drop_index('idx_shift_transfers_to_status', 'shift_transfers')
    op.drop_index('idx_shift_transfers_from_status', 'shift_transfers')
    op.drop_index('idx_shift_transfers_assigned_at', 'shift_transfers')
    op.drop_index('idx_shift_transfers_created_at', 'shift_transfers')
    op.drop_index('idx_shift_transfers_reason', 'shift_transfers')
    op.drop_index('idx_shift_transfers_status', 'shift_transfers')
    op.drop_index('idx_shift_transfers_to_executor', 'shift_transfers')
    op.drop_index('idx_shift_transfers_from_executor', 'shift_transfers')
    op.drop_index('idx_shift_transfers_shift_id', 'shift_transfers')

    # Удаление таблицы
    op.drop_table('shift_transfers')

    print("✅ Таблица shift_transfers успешно удалена")