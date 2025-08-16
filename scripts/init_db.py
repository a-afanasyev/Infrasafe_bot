#!/usr/bin/env python3
"""
Скрипт инициализации базы данных в текущем состоянии.

Что делает:
- Создает все таблицы по текущим моделям SQLAlchemy (`Base.metadata.create_all`) без удаления данных
- Для SQLite делает резервную копию файла БД (по умолчанию)
- Применяет имеющиеся миграции из `uk_management_bot/database/migrations` (идемпотентно)

Запуск (из корня проекта):
  ./uk_management_bot/venv/bin/python scripts/init_db.py

Опции:
  --no-backup         Не создавать резервную копию файла базы данных (для SQLite)
  --skip-migrations   Пропустить применение миграций
  --verbose           Подробный лог

Скрипт НЕ удаляет существующие данные и НЕ пересоздаёт таблицы.
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime


# Настраиваем импорты так же, как в scripts/grant_roles.py,
# чтобы скрипт можно было запускать как из корня, так и из других мест
try:
    from uk_management_bot.database.session import engine, Base
    from uk_management_bot.config.settings import settings
    # Миграции (импортируем функции)
    from uk_management_bot.database.migrations.add_user_addresses import (
        migrate_add_user_addresses,
        check_migration_status as check_addresses_status,
    )
    from uk_management_bot.database.migrations.add_user_roles_active_role import (
        migrate_add_user_roles_active_role,
        check_migration_status as check_roles_status,
    )
except ModuleNotFoundError:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    PKG_DIR = os.path.join(PROJECT_ROOT, "uk_management_bot")
    if PKG_DIR not in sys.path:
        sys.path.insert(0, PKG_DIR)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    from database.session import engine, Base
    from config.settings import settings
    from database.migrations.add_user_addresses import (
        migrate_add_user_addresses,
        check_migration_status as check_addresses_status,
    )
    from database.migrations.add_user_roles_active_role import (
        migrate_add_user_roles_active_role,
        check_migration_status as check_roles_status,
    )


logger = logging.getLogger("init_db")


def is_sqlite_url(db_url: str) -> bool:
    """Проверяет, что используется SQLite (по строке подключения).
    Типичный вид: sqlite:////absolute/path/to/db.sqlite
    """
    return db_url.startswith("sqlite:")


def get_sqlite_db_path_from_url(db_url: str) -> str | None:
    """Достает путь к файлу SQLite из DATABASE_URL. Возвращает None, если не SQLite.
    Пример: sqlite:////tmp/uk_management.db → /tmp/uk_management.db
    """
    if not is_sqlite_url(db_url):
        return None
    # Ожидаем формат sqlite:////absolute/path или sqlite:///relative/path
    # engine.url.database даёт готовый путь, но тут парсим напрямую для простоты совместимости
    # Попробуем получить путь через engine.url.database, если возможно
    try:
        # engine может быть недоступен при раннем импорте в некоторых окружениях
        db_path = engine.url.database  # type: ignore[attr-defined]
        return db_path
    except Exception:
        # Фоллбэк: грубый парсинг строки
        # Убираем префикс sqlite://
        raw = db_url[len("sqlite://"):]
        # Если начинается с одинарного слеша, это относительный путь
        # Если с двойного или более — абсолютный
        if raw.startswith("/"):
            return raw
        return os.path.abspath(raw)


def make_backup_if_needed(db_path: str, no_backup: bool) -> str | None:
    """Создаёт резервную копию файла SQLite, если он существует и резервные копии не отключены.
    Возвращает путь к бэкапу или None.
    """
    if no_backup:
        return None
    if not db_path or db_path == ":memory:" or not os.path.exists(db_path):
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{db_path}.{ts}.bak"
    shutil.copy2(db_path, backup_path)
    logger.info("Создана резервная копия БД: %s", backup_path)
    return backup_path


def apply_migrations_safely() -> dict:
    """Применяет доступные миграции. Возвращает сводный результат.
    Миграции написаны под SQLite и идемпотентны (добавляют колонки, если их нет).
    """
    result = {
        "add_user_addresses": None,
        "add_user_roles_active_role": None,
    }
    # Первая миграция: адреса пользователя
    try:
        migrate_add_user_addresses()
        ok1 = check_addresses_status()
        result["add_user_addresses"] = "ok" if ok1 else "check_failed"
        logger.info("Миграция add_user_addresses: %s", result["add_user_addresses"])
    except Exception as exc:
        logger.error("Ошибка миграции add_user_addresses: %s", exc)
        result["add_user_addresses"] = f"error: {exc}"

    # Вторая миграция: roles/active_role
    try:
        migrate_add_user_roles_active_role()
        ok2 = check_roles_status()
        result["add_user_roles_active_role"] = "ok" if ok2 else "check_failed"
        logger.info("Миграция add_user_roles_active_role: %s", result["add_user_roles_active_role"])
    except Exception as exc:
        logger.error("Ошибка миграции add_user_roles_active_role: %s", exc)
        result["add_user_roles_active_role"] = f"error: {exc}"

    return result


def main():
    parser = argparse.ArgumentParser(description="Инициализация базы данных проекта")
    parser.add_argument("--no-backup", action="store_true", help="Не создавать резервную копию SQLite-файла")
    parser.add_argument("--skip-migrations", action="store_true", help="Не применять миграции (только create_all)")
    parser.add_argument("--verbose", action="store_true", help="Включить подробный лог (DEBUG)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Строка подключения: %s", settings.DATABASE_URL)

    # Если SQLite — делаем бэкап файла базы, если он существует
    sqlite_db_path = get_sqlite_db_path_from_url(settings.DATABASE_URL)
    backup_path = None
    if sqlite_db_path:
        backup_path = make_backup_if_needed(sqlite_db_path, args.no_backup)

    # Создаём все таблицы по текущим моделям
    logger.info("Создание таблиц (если отсутствуют) по моделям SQLAlchemy...")
    Base.metadata.create_all(bind=engine)
    logger.info("Таблицы актуализированы")

    migrations = None
    if not args.skip_migrations and sqlite_db_path:
        # Встроенные миграции ориентируются на расположение файла БД в корне проекта.
        # Чтобы они нашли нужный путь, гарантируем текущую директорию = корень проекта.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, ".."))
        old_cwd = os.getcwd()
        try:
            os.chdir(project_root)
            logger.info("Применение миграций (SQLite)...")
            migrations = apply_migrations_safely()
        finally:
            os.chdir(old_cwd)
    else:
        if args.skip_migrations:
            logger.info("Миграции пропущены по флагу --skip-migrations")
        else:
            logger.info("Миграции не применяются (не SQLite)")

    summary = {
        "database_url": settings.DATABASE_URL,
        "sqlite_db_path": sqlite_db_path,
        "backup": backup_path,
        "migrations": migrations,
        "status": "ok",
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


