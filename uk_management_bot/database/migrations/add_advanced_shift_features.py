"""
Добавление расширенных возможностей для системы смен

Revision ID: add_advanced_shift_features
Revises: add_request_assignment_fields
Create Date: 2025-09-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_advanced_shift_features'
down_revision = 'add_request_assignment_fields'
branch_labels = None
depends_on = None


def upgrade():
    """Применение миграции - добавление новых полей и таблиц для системы смен"""
    
    # ========== РАСШИРЕНИЕ ТАБЛИЦЫ SHIFTS ==========
    print("🔄 Расширение таблицы shifts...")
    
    # Новые поля планирования
    op.add_column('shifts', sa.Column('planned_start_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shifts', sa.Column('planned_end_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shifts', sa.Column('shift_template_id', sa.Integer(), nullable=True))
    op.add_column('shifts', sa.Column('shift_type', sa.String(50), nullable=True, server_default='regular'))
    
    # Новые поля специализации
    op.add_column('shifts', sa.Column('specialization_focus', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('shifts', sa.Column('coverage_areas', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('shifts', sa.Column('geographic_zone', sa.String(100), nullable=True))
    
    # Новые поля планирования нагрузки
    op.add_column('shifts', sa.Column('max_requests', sa.Integer(), nullable=False, server_default='10'))
    op.add_column('shifts', sa.Column('current_request_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('shifts', sa.Column('priority_level', sa.Integer(), nullable=False, server_default='1'))
    
    # Новые поля аналитики производительности
    op.add_column('shifts', sa.Column('completed_requests', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('shifts', sa.Column('average_completion_time', sa.Float(), nullable=True))
    op.add_column('shifts', sa.Column('average_response_time', sa.Float(), nullable=True))
    op.add_column('shifts', sa.Column('efficiency_score', sa.Float(), nullable=True))
    op.add_column('shifts', sa.Column('quality_rating', sa.Float(), nullable=True))
    
    print("✅ Таблица shifts расширена")
    
    # ========== СОЗДАНИЕ ТАБЛИЦЫ SHIFT_TEMPLATES ==========
    print("🔄 Создание таблицы shift_templates...")
    
    op.create_table(
        'shift_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        
        # Временные рамки
        sa.Column('start_hour', sa.Integer(), nullable=False),
        sa.Column('start_minute', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_hours', sa.Integer(), nullable=False, server_default='8'),
        
        # Требования к исполнителям
        sa.Column('required_specializations', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('min_executors', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_executors', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('default_max_requests', sa.Integer(), nullable=False, server_default='10'),
        
        # Зоны покрытия
        sa.Column('coverage_areas', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('geographic_zone', sa.String(100), nullable=True),
        sa.Column('priority_level', sa.Integer(), nullable=False, server_default='1'),
        
        # Автоматизация
        sa.Column('auto_create', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('days_of_week', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('advance_days', sa.Integer(), nullable=False, server_default='7'),
        
        # Дополнительные настройки
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('default_shift_type', sa.String(50), nullable=False, server_default='regular'),
        sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        
        # Системные поля
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    print("✅ Таблица shift_templates создана")
    
    # ========== СОЗДАНИЕ ТАБЛИЦЫ SHIFT_SCHEDULES ==========
    print("🔄 Создание таблицы shift_schedules...")
    
    op.create_table(
        'shift_schedules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.Date(), nullable=False, unique=True),
        
        # Планирование покрытия
        sa.Column('planned_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('actual_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('planned_specialization_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('actual_specialization_coverage', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        
        # Прогнозы и планирование
        sa.Column('predicted_requests', sa.Integer(), nullable=True),
        sa.Column('actual_requests', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('prediction_accuracy', sa.Float(), nullable=True),
        sa.Column('recommended_shifts', sa.Integer(), nullable=True),
        sa.Column('actual_shifts', sa.Integer(), nullable=False, server_default='0'),
        
        # Оптимизация
        sa.Column('optimization_score', sa.Float(), nullable=True),
        sa.Column('coverage_percentage', sa.Float(), nullable=True),
        sa.Column('load_balance_score', sa.Float(), nullable=True),
        
        # Дополнительная информация
        sa.Column('special_conditions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('manual_adjustments', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('notes', sa.String(500), nullable=True),
        
        # Статус и метаданные
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('auto_generated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        
        # Системные поля
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    print("✅ Таблица shift_schedules создана")
    
    # ========== СОЗДАНИЕ ТАБЛИЦЫ SHIFT_ASSIGNMENTS ==========
    print("🔄 Создание таблицы shift_assignments...")
    
    op.create_table(
        'shift_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        
        # Основные связи
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('request_number', sa.String(10), nullable=False),
        
        # Приоритизация и планирование
        sa.Column('assignment_priority', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('estimated_duration', sa.Integer(), nullable=True),
        sa.Column('assignment_order', sa.Integer(), nullable=True),
        
        # ML-оптимизация и оценки
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('confidence_level', sa.Float(), nullable=True),
        sa.Column('specialization_match_score', sa.Float(), nullable=True),
        sa.Column('geographic_score', sa.Float(), nullable=True),
        sa.Column('workload_score', sa.Float(), nullable=True),
        
        # Статус и выполнение
        sa.Column('status', sa.String(50), nullable=False, server_default='assigned'),
        sa.Column('auto_assigned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('confirmed_by_executor', sa.Boolean(), nullable=False, server_default='false'),
        
        # Временные метки
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('planned_start_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('planned_completion_at', sa.DateTime(timezone=True), nullable=True),
        
        # Дополнительная информация
        sa.Column('assignment_reason', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('executor_instructions', sa.Text(), nullable=True),
        
        # Результаты выполнения
        sa.Column('actual_duration', sa.Integer(), nullable=True),
        sa.Column('execution_quality_rating', sa.Float(), nullable=True),
        sa.Column('had_issues', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('issues_description', sa.Text(), nullable=True),
        
        # Системные поля
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    print("✅ Таблица shift_assignments создана")
    
    # ========== СОЗДАНИЕ ИНДЕКСОВ ==========
    print("🔄 Создание индексов для производительности...")
    
    # Индексы для shifts
    op.create_index('idx_shifts_planned_start', 'shifts', ['planned_start_time'])
    op.create_index('idx_shifts_shift_type', 'shifts', ['shift_type'])
    op.create_index('idx_shifts_priority', 'shifts', ['priority_level'])
    op.create_index('idx_shifts_template_id', 'shifts', ['shift_template_id'])
    
    # Индексы для shift_schedules
    op.create_index('idx_shift_schedules_date', 'shift_schedules', ['date'])
    op.create_index('idx_shift_schedules_status', 'shift_schedules', ['status'])
    op.create_index('idx_shift_schedules_created_by', 'shift_schedules', ['created_by'])
    
    # Индексы для shift_assignments
    op.create_index('idx_shift_assignments_shift_id', 'shift_assignments', ['shift_id'])
    op.create_index('idx_shift_assignments_request_number', 'shift_assignments', ['request_number'])
    op.create_index('idx_shift_assignments_status', 'shift_assignments', ['status'])
    op.create_index('idx_shift_assignments_assigned_at', 'shift_assignments', ['assigned_at'])
    op.create_index('idx_shift_assignments_priority', 'shift_assignments', ['assignment_priority'])
    
    # Составные индексы для оптимизации запросов
    op.create_index('idx_shifts_status_type', 'shifts', ['status', 'shift_type'])
    op.create_index('idx_assignments_shift_status', 'shift_assignments', ['shift_id', 'status'])
    
    print("✅ Индексы созданы")
    
    # ========== СОЗДАНИЕ ВНЕШНИХ КЛЮЧЕЙ ==========
    print("🔄 Создание внешних ключей...")
    
    # Внешние ключи для shifts
    op.create_foreign_key(
        'fk_shifts_template_id', 'shifts', 'shift_templates', 
        ['shift_template_id'], ['id'], ondelete='SET NULL'
    )
    
    # Внешние ключи для shift_schedules
    op.create_foreign_key(
        'fk_shift_schedules_created_by', 'shift_schedules', 'users',
        ['created_by'], ['id'], ondelete='SET NULL'
    )
    
    # Внешние ключи для shift_assignments
    op.create_foreign_key(
        'fk_shift_assignments_shift_id', 'shift_assignments', 'shifts',
        ['shift_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_shift_assignments_request_number', 'shift_assignments', 'requests',
        ['request_number'], ['request_number'], ondelete='CASCADE'
    )
    
    print("✅ Внешние ключи созданы")
    
    # ========== ОБНОВЛЕНИЕ СУЩЕСТВУЮЩИХ ДАННЫХ ==========
    print("🔄 Обновление существующих данных...")
    
    # Устанавливаем значения по умолчанию для существующих смен
    op.execute("""
        UPDATE shifts 
        SET 
            shift_type = 'regular',
            max_requests = 10,
            current_request_count = 0,
            priority_level = 1,
            completed_requests = 0
        WHERE shift_type IS NULL
    """)
    
    print("✅ Существующие данные обновлены")
    print("🎉 Миграция успешно применена!")


def downgrade():
    """Откат миграции - удаление новых полей и таблиц"""
    
    print("🔄 Откат миграции...")
    
    # Удаление внешних ключей
    op.drop_constraint('fk_shifts_template_id', 'shifts', type_='foreignkey')
    op.drop_constraint('fk_shift_schedules_created_by', 'shift_schedules', type_='foreignkey')
    op.drop_constraint('fk_shift_assignments_shift_id', 'shift_assignments', type_='foreignkey')
    op.drop_constraint('fk_shift_assignments_request_number', 'shift_assignments', type_='foreignkey')
    
    # Удаление индексов
    op.drop_index('idx_shifts_planned_start', 'shifts')
    op.drop_index('idx_shifts_shift_type', 'shifts')
    op.drop_index('idx_shifts_priority', 'shifts')
    op.drop_index('idx_shifts_template_id', 'shifts')
    op.drop_index('idx_shift_schedules_date', 'shift_schedules')
    op.drop_index('idx_shift_schedules_status', 'shift_schedules')
    op.drop_index('idx_shift_schedules_created_by', 'shift_schedules')
    op.drop_index('idx_shift_assignments_shift_id', 'shift_assignments')
    op.drop_index('idx_shift_assignments_request_number', 'shift_assignments')
    op.drop_index('idx_shift_assignments_status', 'shift_assignments')
    op.drop_index('idx_shift_assignments_assigned_at', 'shift_assignments')
    op.drop_index('idx_shift_assignments_priority', 'shift_assignments')
    op.drop_index('idx_shifts_status_type', 'shifts')
    op.drop_index('idx_assignments_shift_status', 'shift_assignments')
    
    # Удаление таблиц
    op.drop_table('shift_assignments')
    op.drop_table('shift_schedules')
    op.drop_table('shift_templates')
    
    # Удаление новых полей из shifts
    columns_to_drop = [
        'planned_start_time', 'planned_end_time', 'shift_template_id', 'shift_type',
        'specialization_focus', 'coverage_areas', 'geographic_zone',
        'max_requests', 'current_request_count', 'priority_level',
        'completed_requests', 'average_completion_time', 'average_response_time',
        'efficiency_score', 'quality_rating'
    ]
    
    for column in columns_to_drop:
        op.drop_column('shifts', column)
    
    print("✅ Откат миграции завершен")