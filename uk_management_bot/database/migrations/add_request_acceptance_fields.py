"""
Миграция для добавления полей системы приёмки заявок

Добавляет поля для:
- Возврата заявок заявителем
- Подтверждения выполнения менеджером
- Отслеживания истории приёмки

Дата: 13 октября 2025
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


def upgrade():
    """Добавление полей для системы приёмки заявок"""

    # Поля для возврата заявок заявителем
    op.add_column('requests', sa.Column('is_returned', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('requests', sa.Column('return_reason', sa.Text(), nullable=True))
    op.add_column('requests', sa.Column('return_media', JSON, nullable=True))
    op.add_column('requests', sa.Column('returned_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('requests', sa.Column('returned_by', sa.Integer(), nullable=True))

    # Поля для подтверждения менеджером
    op.add_column('requests', sa.Column('manager_confirmed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('requests', sa.Column('manager_confirmed_by', sa.Integer(), nullable=True))
    op.add_column('requests', sa.Column('manager_confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('requests', sa.Column('manager_confirmation_notes', sa.Text(), nullable=True))

    # Создание внешних ключей
    op.create_foreign_key(
        'fk_requests_returned_by_users',
        'requests', 'users',
        ['returned_by'], ['id'],
        ondelete='SET NULL'
    )

    op.create_foreign_key(
        'fk_requests_manager_confirmed_by_users',
        'requests', 'users',
        ['manager_confirmed_by'], ['id'],
        ondelete='SET NULL'
    )

    # Создание индексов для оптимизации запросов
    op.create_index('idx_requests_is_returned', 'requests', ['is_returned'])
    op.create_index('idx_requests_manager_confirmed', 'requests', ['manager_confirmed'])


def downgrade():
    """Откат миграции"""

    # Удаление индексов
    op.drop_index('idx_requests_manager_confirmed', table_name='requests')
    op.drop_index('idx_requests_is_returned', table_name='requests')

    # Удаление внешних ключей
    op.drop_constraint('fk_requests_manager_confirmed_by_users', 'requests', type_='foreignkey')
    op.drop_constraint('fk_requests_returned_by_users', 'requests', type_='foreignkey')

    # Удаление полей подтверждения менеджером
    op.drop_column('requests', 'manager_confirmation_notes')
    op.drop_column('requests', 'manager_confirmed_at')
    op.drop_column('requests', 'manager_confirmed_by')
    op.drop_column('requests', 'manager_confirmed')

    # Удаление полей возврата заявок
    op.drop_column('requests', 'returned_by')
    op.drop_column('requests', 'returned_at')
    op.drop_column('requests', 'return_media')
    op.drop_column('requests', 'return_reason')
    op.drop_column('requests', 'is_returned')
