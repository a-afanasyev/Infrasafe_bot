import sqlite3
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_db_path():
    """Получить путь к базе данных (локальная SQLite)"""
    possible_paths = [
        "uk_management.db",
        "database/uk_management.db",
        "../uk_management.db",
        "../../uk_management.db",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return "uk_management.db"


def migrate_add_user_roles_active_role():
    """Миграция: добавить поля roles (TEXT) и active_role (VARCHAR) в users.
    Также выполнить бэконап и безопасный бекфилл значений для совместимости.
    roles хранится как JSON-строка.
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1) Проверяем наличие колонок
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if "roles" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN roles TEXT")
            logger.info("Добавлена колонка roles (TEXT)")

        if "active_role" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN active_role VARCHAR(50)")
            logger.info("Добавлена колонка active_role (VARCHAR(50))")

        # 2) Бекфилл: если roles пусто, заполняем на основе старого поля role
        # Принцип: roles = [role], active_role = role; если role пусто → applicant
        cursor.execute(
            """
            UPDATE users
            SET
                roles = COALESCE(
                    CASE
                        WHEN role IS NOT NULL AND role != '' THEN '["' || role || '"]'
                        ELSE '["applicant"]'
                    END,
                    '["applicant"]'
                ),
                active_role = COALESCE(
                    CASE
                        WHEN role IS NOT NULL AND role != '' THEN role
                        ELSE 'applicant'
                    END,
                    'applicant'
                )
            WHERE roles IS NULL OR roles = '' OR active_role IS NULL OR active_role = ''
            """
        )

        conn.commit()
        logger.info("Миграция add_user_roles_active_role выполнена успешно")

    except Exception as exc:
        logger.error(f"Ошибка миграции add_user_roles_active_role: {exc}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def rollback_add_user_roles_active_role():
    """Откат миграции: удалить roles/active_role (через пересоздание таблицы).
    SQLite не поддерживает DROP COLUMN, поэтому пересоздаём таблицу без новых полей.
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Создаём резервную копию с необходимыми старыми колонками
        cursor.execute(
            """
            CREATE TABLE users_backup AS
            SELECT id, telegram_id, username, first_name, last_name,
                   role, status, language, phone, address,
                   home_address, apartment_address, yard_address, address_type,
                   specialization, created_at, updated_at
            FROM users
            """
        )

        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_backup RENAME TO users")

        conn.commit()
        logger.info("Откат add_user_roles_active_role выполнен успешно")

    except Exception as exc:
        logger.error(f"Ошибка отката add_user_roles_active_role: {exc}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def check_migration_status():
    """Проверить, что поля roles и active_role присутствуют."""
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        missing = [c for c in ["roles", "active_role"] if c not in columns]
        return len(missing) == 0
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "migrate":
        migrate_add_user_roles_active_role()
    elif cmd == "rollback":
        rollback_add_user_roles_active_role()
    elif cmd == "check":
        ok = check_migration_status()
        print("OK" if ok else "MISSING")
    else:
        print("Usage: python add_user_roles_active_role.py [migrate|rollback|check]")


