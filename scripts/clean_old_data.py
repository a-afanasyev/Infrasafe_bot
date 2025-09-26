"""
Скрипт для очистки старых данных перед переходом на новую систему нумерации
Удаляет все заявки и связанные с ними данные
"""

import logging
import sys
import os
from datetime import datetime
from typing import List

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from uk_management_bot.database.session import SessionLocal, engine
from uk_management_bot.database.models.request import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OldDataCleaner:
    """Класс для очистки старых данных"""
    
    def __init__(self):
        self.db = SessionLocal()
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.close()
    
    def get_tables_with_request_references(self) -> List[str]:
        """
        Получает список таблиц, которые ссылаются на requests
        """
        inspector = inspect(engine)
        tables_to_clean = []
        
        for table_name in inspector.get_table_names():
            try:
                foreign_keys = inspector.get_foreign_keys(table_name)
                for fk in foreign_keys:
                    if fk['referred_table'] == 'requests':
                        tables_to_clean.append(table_name)
                        break
            except Exception as e:
                logger.warning(f"Error inspecting table {table_name}: {e}")
        
        return tables_to_clean
    
    def backup_statistics(self) -> dict:
        """
        Создает статистику данных перед удалением
        """
        stats = {
            'timestamp': datetime.now().isoformat(),
            'tables': {}
        }
        
        # Статистика по заявкам
        try:
            request_count = self.db.query(Request).count()
            stats['tables']['requests'] = {
                'count': request_count,
                'note': 'All requests will be deleted'
            }
        except Exception as e:
            logger.error(f"Error getting requests count: {e}")
            stats['tables']['requests'] = {'error': str(e)}
        
        # Статистика по связанным таблицам
        related_tables = self.get_tables_with_request_references()
        for table_name in related_tables:
            try:
                result = self.db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                stats['tables'][table_name] = {
                    'count': count,
                    'note': 'Will be cleaned due to request references'
                }
            except Exception as e:
                logger.error(f"Error getting count for {table_name}: {e}")
                stats['tables'][table_name] = {'error': str(e)}
        
        return stats
    
    def clean_related_tables(self) -> bool:
        """
        Очищает все таблицы, связанные с requests
        """
        logger.info("Cleaning related tables...")
        
        # Определяем порядок очистки (от зависимых к независимым)
        tables_to_clean = [
            'request_comments',      # Комментарии к заявкам
            'request_assignments',   # Назначения заявок
            'shift_assignments',     # Назначения смен (если есть связь)
        ]
        
        cleaned_tables = []
        
        for table_name in tables_to_clean:
            try:
                # Проверяем существование таблицы
                inspector = inspect(engine)
                if table_name not in inspector.get_table_names():
                    logger.info(f"Table {table_name} does not exist, skipping")
                    continue
                
                # Получаем количество записей до очистки
                result = self.db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count_before = result.scalar()
                
                if count_before > 0:
                    # Очищаем таблицу
                    self.db.execute(text(f"DELETE FROM {table_name}"))
                    self.db.commit()
                    
                    logger.info(f"Cleaned table {table_name}: {count_before} records deleted")
                    cleaned_tables.append({
                        'table': table_name,
                        'records_deleted': count_before
                    })
                else:
                    logger.info(f"Table {table_name} is already empty")
                    
            except Exception as e:
                logger.error(f"Error cleaning table {table_name}: {e}")
                self.db.rollback()
                return False
        
        logger.info(f"Successfully cleaned {len(cleaned_tables)} related tables")
        return True
    
    def clean_requests_table(self) -> bool:
        """
        Очищает таблицу requests
        """
        logger.info("Cleaning requests table...")
        
        try:
            # Получаем количество заявок
            request_count = self.db.query(Request).count()
            
            if request_count > 0:
                # Удаляем все заявки
                self.db.query(Request).delete()
                self.db.commit()
                
                logger.info(f"Deleted {request_count} requests from requests table")
            else:
                logger.info("Requests table is already empty")
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning requests table: {e}")
            self.db.rollback()
            return False
    
    def verify_cleanup(self) -> bool:
        """
        Проверяет, что очистка выполнена корректно
        """
        logger.info("Verifying cleanup...")
        
        try:
            # Проверяем, что таблица requests пуста
            request_count = self.db.query(Request).count()
            if request_count > 0:
                logger.error(f"Cleanup verification failed: {request_count} requests still exist")
                return False
            
            # Проверяем связанные таблицы
            related_tables = ['request_comments', 'request_assignments']
            for table_name in related_tables:
                try:
                    inspector = inspect(engine)
                    if table_name in inspector.get_table_names():
                        result = self.db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        count = result.scalar()
                        if count > 0:
                            logger.warning(f"Table {table_name} still has {count} records")
                except Exception as e:
                    logger.warning(f"Could not verify table {table_name}: {e}")
            
            logger.info("Cleanup verification completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during cleanup verification: {e}")
            return False
    
    def run_full_cleanup(self) -> bool:
        """
        Выполняет полную очистку данных
        """
        logger.info("="*60)
        logger.info("STARTING FULL DATA CLEANUP")
        logger.info("="*60)
        
        # Создаем статистику до очистки
        logger.info("Creating backup statistics...")
        stats = self.backup_statistics()
        
        # Выводим что будет удалено
        logger.info("Data to be deleted:")
        for table, info in stats['tables'].items():
            if 'count' in info:
                logger.info(f"  {table}: {info['count']} records")
        
        # Запрашиваем подтверждение
        logger.warning("THIS WILL PERMANENTLY DELETE ALL REQUESTS AND RELATED DATA!")
        
        try:
            # Очищаем связанные таблицы
            if not self.clean_related_tables():
                logger.error("Failed to clean related tables")
                return False
            
            # Очищаем таблицу requests
            if not self.clean_requests_table():
                logger.error("Failed to clean requests table")
                return False
            
            # Проверяем результат
            if not self.verify_cleanup():
                logger.error("Cleanup verification failed")
                return False
            
            logger.info("="*60)
            logger.info("DATA CLEANUP COMPLETED SUCCESSFULLY")
            logger.info("="*60)
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error during cleanup: {e}")
            return False

def main():
    """Главная функция"""
    logger.info("Old Data Cleanup Script")
    logger.info("This script will delete ALL requests and related data")
    
    with OldDataCleaner() as cleaner:
        success = cleaner.run_full_cleanup()
        
        if success:
            logger.info("Cleanup completed successfully!")
            logger.info("The system is now ready for the new request numbering scheme")
            return 0
        else:
            logger.error("Cleanup failed!")
            return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)