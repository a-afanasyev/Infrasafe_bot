"""
Скрипт для применения миграции полей приёмки заявок
"""

import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from uk_management_bot.database.session import engine
from sqlalchemy import text

def apply_migration():
    """Применяет миграцию add_request_acceptance_fields"""

    print("🔄 Применение миграции для полей приёмки заявок...")

    with engine.connect() as conn:
        try:
            # Поля для возврата заявок заявителем
            print("  ➤ Добавление полей возврата заявок...")
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS is_returned BOOLEAN NOT NULL DEFAULT false
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS return_reason TEXT
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS return_media JSONB
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS returned_at TIMESTAMP WITH TIME ZONE
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS returned_by INTEGER
            """))

            # Поля для подтверждения менеджером
            print("  ➤ Добавление полей подтверждения менеджером...")
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS manager_confirmed BOOLEAN NOT NULL DEFAULT false
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS manager_confirmed_by INTEGER
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS manager_confirmed_at TIMESTAMP WITH TIME ZONE
            """))
            conn.execute(text("""
                ALTER TABLE requests
                ADD COLUMN IF NOT EXISTS manager_confirmation_notes TEXT
            """))

            # Создание внешних ключей
            print("  ➤ Создание внешних ключей...")

            # Проверяем существование FK перед созданием
            result = conn.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'requests'
                AND constraint_name = 'fk_requests_returned_by_users'
            """))

            if result.fetchone() is None:
                conn.execute(text("""
                    ALTER TABLE requests
                    ADD CONSTRAINT fk_requests_returned_by_users
                    FOREIGN KEY (returned_by) REFERENCES users(id) ON DELETE SET NULL
                """))

            result = conn.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'requests'
                AND constraint_name = 'fk_requests_manager_confirmed_by_users'
            """))

            if result.fetchone() is None:
                conn.execute(text("""
                    ALTER TABLE requests
                    ADD CONSTRAINT fk_requests_manager_confirmed_by_users
                    FOREIGN KEY (manager_confirmed_by) REFERENCES users(id) ON DELETE SET NULL
                """))

            # Создание индексов
            print("  ➤ Создание индексов...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_requests_is_returned
                ON requests(is_returned)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_requests_manager_confirmed
                ON requests(manager_confirmed)
            """))

            conn.commit()

            print("✅ Миграция успешно применена!")

        except Exception as e:
            conn.rollback()
            print(f"❌ Ошибка при применении миграции: {e}")
            raise

if __name__ == "__main__":
    apply_migration()
