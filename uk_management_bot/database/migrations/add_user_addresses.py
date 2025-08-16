import sqlite3
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

def get_db_path():
    """Получить путь к базе данных"""
    # Ищем файл базы данных в различных возможных местах
    possible_paths = [
        "uk_management.db",
        "database/uk_management.db",
        "../uk_management.db",
        "../../uk_management.db"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Если не найден, возвращаем путь по умолчанию
    return "uk_management.db"

def migrate_add_user_addresses():
    """Миграция для добавления полей адресов в таблицу users"""
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, существуют ли уже новые колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Добавляем новые колонки только если их еще нет
        if 'home_address' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN home_address TEXT")
            logger.info("Добавлена колонка home_address")
        
        if 'apartment_address' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN apartment_address TEXT")
            logger.info("Добавлена колонка apartment_address")
        
        if 'yard_address' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN yard_address TEXT")
            logger.info("Добавлена колонка yard_address")
        
        if 'address_type' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN address_type VARCHAR(20)")
            logger.info("Добавлена колонка address_type")
        
        # Обновляем существующие данные (опционально)
        # Если у пользователя есть адрес в старом поле, устанавливаем его как home_address
        cursor.execute("""
            UPDATE users 
            SET address_type = 'home', home_address = address 
            WHERE address IS NOT NULL AND home_address IS NULL
        """)
        
        conn.commit()
        logger.info("Миграция add_user_addresses выполнена успешно")
        
    except Exception as e:
        logger.error(f"Ошибка миграции add_user_addresses: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def rollback_add_user_addresses():
    """Откат миграции add_user_addresses"""
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # SQLite не поддерживает DROP COLUMN, поэтому создаем новую таблицу
        # Создаем резервную копию текущей таблицы
        cursor.execute("""
            CREATE TABLE users_backup AS 
            SELECT id, telegram_id, username, first_name, last_name, 
                   role, status, language, phone, address, 
                   created_at, updated_at 
            FROM users
        """)
        
        # Удаляем старую таблицу
        cursor.execute("DROP TABLE users")
        
        # Переименовываем резервную копию
        cursor.execute("ALTER TABLE users_backup RENAME TO users")
        
        conn.commit()
        logger.info("Откат миграции add_user_addresses выполнен успешно")
        
    except Exception as e:
        logger.error(f"Ошибка отката миграции add_user_addresses: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def check_migration_status():
    """Проверить статус миграции"""
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        required_columns = ['home_address', 'apartment_address', 'yard_address', 'address_type']
        missing_columns = [col for col in required_columns if col not in columns]
        
        if missing_columns:
            logger.warning(f"Отсутствуют колонки: {missing_columns}")
            return False
        else:
            logger.info("Все необходимые колонки присутствуют")
            return True
            
    except Exception as e:
        logger.error(f"Ошибка проверки статуса миграции: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "migrate":
            migrate_add_user_addresses()
        elif command == "rollback":
            rollback_add_user_addresses()
        elif command == "check":
            check_migration_status()
        else:
            print("Использование: python add_user_addresses.py [migrate|rollback|check]")
    else:
        print("Использование: python add_user_addresses.py [migrate|rollback|check]") 