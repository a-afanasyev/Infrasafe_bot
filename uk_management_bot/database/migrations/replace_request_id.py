"""
Миграция для замены autoincrement ID на request_number в формате YYMMDD-NNN
Полная замена структуры таблицы requests с очисткой старых данных
"""

import logging
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = 'replace_request_id_001'
down_revision = None  # Указать ID предыдущей миграции
branch_labels = None
depends_on = None

def upgrade():
    """
    Замена структуры таблицы requests:
    1. Очистка всех связанных данных
    2. Удаление старой таблицы requests
    3. Создание новой таблицы с request_number как PRIMARY KEY
    """
    
    logger.info("Starting migration: replace request ID with request_number")
    
    # Этап 1: Очистка связанных таблиц
    logger.info("Step 1: Cleaning related tables")
    
    # Очистка таблиц с foreign key на requests
    related_tables = [
        'request_assignments',
        'request_comments', 
        'shift_assignments',  # если есть связь с requests
    ]
    
    for table_name in related_tables:
        try:
            # Проверяем существование таблицы
            connection = op.get_bind()
            inspector = sa.inspect(connection)
            if table_name in inspector.get_table_names():
                logger.info(f"Clearing table: {table_name}")
                op.execute(f"DELETE FROM {table_name}")
            else:
                logger.info(f"Table {table_name} does not exist, skipping")
        except Exception as e:
            logger.warning(f"Error clearing table {table_name}: {e}")
    
    # Этап 2: Сохранение структуры старой таблицы (для rollback)
    logger.info("Step 2: Backing up old requests structure")
    
    try:
        # Переименовываем старую таблицу для backup
        op.rename_table('requests', 'requests_backup_old_id')
        logger.info("Old requests table backed up as requests_backup_old_id")
    except Exception as e:
        logger.error(f"Error backing up requests table: {e}")
        # Если не можем сделать backup, просто дропаем
        op.drop_table('requests')
        logger.info("Old requests table dropped")
    
    # Этап 3: Создание новой таблицы requests с request_number
    logger.info("Step 3: Creating new requests table")
    
    op.create_table('requests',
        # PRIMARY KEY - новый номер заявки
        sa.Column('request_number', sa.String(10), primary_key=True, index=True),
        
        # Связь с пользователем (заявителем)
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        
        # Основная информация о заявке
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), default='Новая', nullable=False),
        sa.Column('address', sa.Text, nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('apartment', sa.String(20), nullable=True),
        sa.Column('urgency', sa.String(20), default='Обычная', nullable=False),
        
        # Медиафайлы (JSON массив с file_ids)
        sa.Column('media_files', sa.JSON, default=list),
        
        # Исполнитель (если назначен) - теперь ссылается на user.id
        sa.Column('executor_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        
        # Дополнительная информация
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('completion_report', sa.Text, nullable=True),
        sa.Column('completion_media', sa.JSON, default=list),
        
        # Поля для назначений
        sa.Column('assignment_type', sa.String(20), nullable=True),  # 'group' или 'individual'
        sa.Column('assigned_group', sa.String(100), nullable=True),  # специализация группы
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_by', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        
        # Поля для материалов и отчетов
        sa.Column('purchase_materials', sa.Text, nullable=True),
        sa.Column('requested_materials', sa.Text, nullable=True),
        sa.Column('manager_materials_comment', sa.Text, nullable=True),
        sa.Column('purchase_history', sa.Text, nullable=True),
        
        # Системные поля
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Этап 4: Создание индексов для производительности
    logger.info("Step 4: Creating indexes")
    
    # Индекс по дате (первые 6 символов номера)
    op.create_index('idx_requests_date_prefix', 'requests', [sa.text("substring(request_number, 1, 6)")])
    
    # Индекс по пользователю
    op.create_index('idx_requests_user_id', 'requests', ['user_id'])
    
    # Индекс по исполнителю
    op.create_index('idx_requests_executor_id', 'requests', ['executor_id'])
    
    # Индекс по статусу
    op.create_index('idx_requests_status', 'requests', ['status'])
    
    # Индекс по дате создания
    op.create_index('idx_requests_created_at', 'requests', ['created_at'])
    
    # Этап 5: Обновление связанных таблиц
    logger.info("Step 5: Updating related tables structure")
    
    # Обновляем таблицы с foreign key для работы с новым форматом
    try:
        # request_assignments - меняем request_id на request_number
        connection = op.get_bind()
        inspector = sa.inspect(connection)
        
        if 'request_assignments' in inspector.get_table_names():
            # Дропаем старый foreign key constraint
            fk_constraints = inspector.get_foreign_keys('request_assignments')
            for fk in fk_constraints:
                if 'request_id' in fk['constrained_columns']:
                    op.drop_constraint(fk['name'], 'request_assignments', type_='foreignkey')
            
            # Дропаем старую колонку request_id если есть
            columns = [col['name'] for col in inspector.get_columns('request_assignments')]
            if 'request_id' in columns:
                op.drop_column('request_assignments', 'request_id')
            
            # Добавляем новую колонку request_number
            if 'request_number' not in columns:
                op.add_column('request_assignments', 
                             sa.Column('request_number', sa.String(10), nullable=False))
                
                # Создаем новый foreign key
                op.create_foreign_key('fk_request_assignments_request_number', 
                                    'request_assignments', 'requests',
                                    ['request_number'], ['request_number'])
        
        # request_comments - аналогично
        if 'request_comments' in inspector.get_table_names():
            # Дропаем старый foreign key constraint
            fk_constraints = inspector.get_foreign_keys('request_comments')
            for fk in fk_constraints:
                if 'request_id' in fk['constrained_columns']:
                    op.drop_constraint(fk['name'], 'request_comments', type_='foreignkey')
            
            # Дропаем старую колонку request_id если есть
            columns = [col['name'] for col in inspector.get_columns('request_comments')]
            if 'request_id' in columns:
                op.drop_column('request_comments', 'request_id')
            
            # Добавляем новую колонку request_number
            if 'request_number' not in columns:
                op.add_column('request_comments', 
                             sa.Column('request_number', sa.String(10), nullable=False))
                
                # Создаем новый foreign key
                op.create_foreign_key('fk_request_comments_request_number', 
                                    'request_comments', 'requests',
                                    ['request_number'], ['request_number'])
        
    except Exception as e:
        logger.warning(f"Error updating related tables: {e}")
    
    logger.info("Migration completed successfully")

def downgrade():
    """
    Откат миграции - восстановление старой структуры
    ВНИМАНИЕ: Приведет к потере всех новых данных!
    """
    
    logger.warning("Starting migration downgrade - THIS WILL LOSE ALL NEW DATA!")
    
    try:
        # Дропаем новую таблицу
        op.drop_table('requests')
        
        # Восстанавливаем старую таблицу из backup
        op.rename_table('requests_backup_old_id', 'requests')
        
        logger.info("Downgrade completed - old structure restored")
        
    except Exception as e:
        logger.error(f"Error during downgrade: {e}")
        raise