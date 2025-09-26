"""
Миграция для добавления таблиц квартального планирования смен.

Добавляет:
- quarterly_plans - кварталные планы смен
- shift_schedules - запланированные смены в рамках квартального плана
- planning_conflicts - конфликты планирования

Дата создания: 2024-01-15
"""

from sqlalchemy import text


def upgrade(engine):
    """Применяет миграцию - создает новые таблицы."""
    with engine.connect() as conn:
        # Создаем таблицу quarterly_plans
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS quarterly_plans (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                quarter INTEGER NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                created_by INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                specializations TEXT,
                coverage_24_7 BOOLEAN NOT NULL DEFAULT FALSE,
                load_balancing_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                auto_transfers_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                total_shifts_planned INTEGER NOT NULL DEFAULT 0,
                total_hours_planned REAL NOT NULL DEFAULT 0.0,
                coverage_percentage REAL NOT NULL DEFAULT 0.0,
                total_conflicts INTEGER NOT NULL DEFAULT 0,
                resolved_conflicts INTEGER NOT NULL DEFAULT 0,
                pending_conflicts INTEGER NOT NULL DEFAULT 0,
                settings TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                activated_at TIMESTAMP,
                archived_at TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id),
                UNIQUE(year, quarter)
            )
        """))
        
        # Создаем таблицу quarterly_shift_schedules (для квартального планирования)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS quarterly_shift_schedules (
                id INTEGER PRIMARY KEY,
                quarterly_plan_id INTEGER NOT NULL,
                planned_date DATE NOT NULL,
                planned_start_time TIMESTAMP NOT NULL,
                planned_end_time TIMESTAMP NOT NULL,
                assigned_user_id INTEGER,
                specialization VARCHAR(100) NOT NULL,
                schedule_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'planned',
                actual_shift_id INTEGER,
                shift_config TEXT,
                coverage_areas TEXT,
                priority INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (quarterly_plan_id) REFERENCES quarterly_plans (id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_user_id) REFERENCES users (id),
                FOREIGN KEY (actual_shift_id) REFERENCES shifts (id),
                INDEX idx_quarterly_shift_schedules_date (planned_date),
                INDEX idx_quarterly_shift_schedules_user (assigned_user_id),
                INDEX idx_quarterly_shift_schedules_specialization (specialization)
            )
        """))
        
        # Создаем таблицу planning_conflicts
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS planning_conflicts (
                id INTEGER PRIMARY KEY,
                quarterly_plan_id INTEGER NOT NULL,
                conflict_type VARCHAR(100) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                involved_schedule_ids TEXT,
                involved_user_ids TEXT,
                conflict_time TIMESTAMP,
                conflict_date DATE,
                conflict_details TEXT,
                description TEXT,
                suggested_resolutions TEXT,
                applied_resolution TEXT,
                resolved_at TIMESTAMP,
                resolved_by INTEGER,
                priority INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (quarterly_plan_id) REFERENCES quarterly_plans (id) ON DELETE CASCADE,
                FOREIGN KEY (resolved_by) REFERENCES users (id),
                INDEX idx_planning_conflicts_type (conflict_type),
                INDEX idx_planning_conflicts_status (status),
                INDEX idx_planning_conflicts_date (conflict_date)
            )
        """))
        
        # Создаем индексы для оптимизации производительности
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_quarterly_plans_period 
            ON quarterly_plans (year, quarter)
        """))
        
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_quarterly_plans_status 
            ON quarterly_plans (status)
        """))
        
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_quarterly_plans_dates 
            ON quarterly_plans (start_date, end_date)
        """))
        
        conn.commit()
        print("✅ Таблицы квартального планирования созданы успешно")


def downgrade(engine):
    """Откатывает миграцию - удаляет созданные таблицы."""
    with engine.connect() as conn:
        # Удаляем таблицы в обратном порядке из-за внешних ключей
        conn.execute(text("DROP TABLE IF EXISTS planning_conflicts"))
        conn.execute(text("DROP TABLE IF EXISTS quarterly_shift_schedules"))
        conn.execute(text("DROP TABLE IF EXISTS quarterly_plans"))
        
        conn.commit()
        print("✅ Таблицы квартального планирования удалены")


def get_migration_info():
    """Возвращает информацию о миграции."""
    return {
        "version": "20240115_001",
        "description": "Добавление таблиц квартального планирования смен",
        "tables_created": [
            "quarterly_plans",
            "quarterly_shift_schedules", 
            "planning_conflicts"
        ],
        "dependencies": [
            "users",
            "shifts"
        ]
    }


if __name__ == "__main__":
    # Тестирование миграции
    import sys
    import os
    
    # Добавляем путь к проекту
    sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))
    
    from sqlalchemy import create_engine
    from uk_management_bot.database.session import get_database_url
    
    engine = create_engine(get_database_url())
    
    print("Применение миграции для квартального планирования...")
    upgrade(engine)
    print("Миграция применена успешно!")
    
    # Для тестирования отката раскомментируйте:
    # print("Откат миграции...")
    # downgrade(engine)
    # print("Откат выполнен!")