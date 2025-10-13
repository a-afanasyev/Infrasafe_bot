"""
Миграция для обновления полей модели Apartment.

Изменения:
- Переименование поля rooms → rooms_count (для соответствия спецификации)
- Добавление поля area (Float) - площадь квартиры в кв.м

Дата создания: 2025-01-21
"""

from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def upgrade(engine):
    """
    Применяет миграцию - обновляет таблицу apartments.

    ВНИМАНИЕ: Эта миграция предназначена для обновления СУЩЕСТВУЮЩИХ БД.
    На чистой установке add_address_directory.py уже создаст правильную схему,
    поэтому проверяем существование колонки rooms перед переименованием.
    """
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            logger.info("Начало миграции: обновление полей apartments")

            # 1. Проверяем существование колонки rooms и переименовываем при необходимости
            logger.info("Проверка существования колонки rooms...")
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'apartments' AND column_name = 'rooms'
            """))

            if result.fetchone():
                logger.info("Колонка rooms существует, переименовываем в rooms_count...")
                conn.execute(text("""
                    ALTER TABLE apartments
                    RENAME COLUMN rooms TO rooms_count
                """))
            else:
                logger.info("Колонка rooms не найдена, пропускаем переименование (вероятно, чистая установка)")

            # 2. Добавляем колонку area (если её нет)
            logger.info("Добавление колонки area...")
            conn.execute(text("""
                ALTER TABLE apartments
                ADD COLUMN IF NOT EXISTS area FLOAT
            """))

            transaction.commit()
            logger.info("Миграция успешно завершена")

        except Exception as e:
            transaction.rollback()
            logger.error(f"Ошибка при выполнении миграции: {e}")
            raise


def downgrade(engine):
    """Откатывает миграцию - возвращает старые поля."""
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            logger.info("Начало отката миграции: возврат старых полей apartments")

            # 1. Удаляем колонку area
            logger.info("Удаление колонки area...")
            conn.execute(text("""
                ALTER TABLE apartments
                DROP COLUMN IF EXISTS area
            """))

            # 2. Переименовываем колонку rooms_count → rooms
            logger.info("Переименование колонки rooms_count → rooms...")
            conn.execute(text("""
                ALTER TABLE apartments
                RENAME COLUMN rooms_count TO rooms
            """))

            transaction.commit()
            logger.info("Откат миграции успешно завершен")

        except Exception as e:
            transaction.rollback()
            logger.error(f"Ошибка при откате миграции: {e}")
            raise
