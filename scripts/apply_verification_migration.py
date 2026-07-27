#!/usr/bin/env python3
"""
Скрипт для применения миграции системы верификации пользователей

Выполняет:
1. Применение миграции базы данных
2. Проверку создания таблиц
3. Инициализацию базовых данных
"""

import sys
import logging
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from uk_management_bot.database.migrations.add_user_verification_tables import upgrade, downgrade
from uk_management_bot.database.session import engine
from sqlalchemy import text

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_tables_exist():
    """Проверить существование созданных таблиц"""
    try:
        with engine.connect() as conn:
            # Проверяем таблицы
            tables_to_check = [
                'user_documents',
                'user_verifications', 
                'access_rights'
            ]
            
            for table in tables_to_check:
                result = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = '{table}'
                    );
                """))
                exists = result.scalar()
                
                if exists:
                    logger.info(f"✅ Таблица {table} существует")
                else:
                    logger.error(f"❌ Таблица {table} не найдена")
                    return False
            
            # Проверяем поля в таблице users
            fields_to_check = [
                'verification_status',
                'verification_notes',
                'verification_date',
                'verified_by',
                'passport_series',
                'passport_number',
                'birth_date'
            ]
            
            for field in fields_to_check:
                result = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'users' 
                        AND column_name = '{field}'
                    );
                """))
                exists = result.scalar()
                
                if exists:
                    logger.info(f"✅ Поле {field} в таблице users существует")
                else:
                    logger.error(f"❌ Поле {field} в таблице users не найдено")
                    return False
            
            return True
            
    except Exception as e:
        logger.error(f"Ошибка проверки таблиц: {e}")
        return False


def check_indexes_exist():
    """Проверить существование индексов"""
    try:
        with engine.connect() as conn:
            indexes_to_check = [
                'idx_user_documents_user_id',
                'idx_user_documents_status',
                'idx_user_verifications_user_id',
                'idx_user_verifications_status',
                'idx_access_rights_user_id',
                'idx_access_rights_level',
                'idx_access_rights_active'
            ]
            
            for index in indexes_to_check:
                result = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE indexname = '{index}'
                    );
                """))
                exists = result.scalar()
                
                if exists:
                    logger.info(f"✅ Индекс {index} существует")
                else:
                    logger.warning(f"⚠️ Индекс {index} не найден")
            
            return True
            
    except Exception as e:
        logger.error(f"Ошибка проверки индексов: {e}")
        return False


def check_triggers_exist():
    """Проверить существование триггеров"""
    try:
        with engine.connect() as conn:
            triggers_to_check = [
                'update_user_documents_updated_at',
                'update_user_verifications_updated_at',
                'update_access_rights_updated_at'
            ]
            
            for trigger in triggers_to_check:
                result = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM pg_trigger 
                        WHERE tgname = '{trigger}'
                    );
                """))
                exists = result.scalar()
                
                if exists:
                    logger.info(f"✅ Триггер {trigger} существует")
                else:
                    logger.warning(f"⚠️ Триггер {trigger} не найден")
            
            return True
            
    except Exception as e:
        logger.error(f"Ошибка проверки триггеров: {e}")
        return False


def main():
    """Главная функция"""
    logger.info("🚀 Начало применения миграции системы верификации")
    
    try:
        # Применяем миграцию
        logger.info("📋 Применение миграции...")
        upgrade()
        logger.info("✅ Миграция применена успешно")
        
        # Проверяем создание таблиц
        logger.info("🔍 Проверка создания таблиц...")
        if check_tables_exist():
            logger.info("✅ Все таблицы созданы успешно")
        else:
            logger.error("❌ Ошибка создания таблиц")
            return False
        
        # Проверяем индексы
        logger.info("🔍 Проверка индексов...")
        check_indexes_exist()
        
        # Проверяем триггеры
        logger.info("🔍 Проверка триггеров...")
        check_triggers_exist()
        
        logger.info("🎉 Миграция системы верификации завершена успешно!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка применения миграции: {e}")
        return False


def rollback():
    """Откат миграции"""
    logger.info("🔄 Начало отката миграции системы верификации")
    
    try:
        downgrade()
        logger.info("✅ Откат миграции завершен успешно")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка отката миграции: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Скрипт миграции системы верификации")
    parser.add_argument(
        "--rollback", 
        action="store_true", 
        help="Откатить миграцию"
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        success = rollback()
    else:
        success = main()
    
    sys.exit(0 if success else 1)
