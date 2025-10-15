#!/usr/bin/env python3
"""
Скрипт инициализации администратора
Создает пользователя-администратора из переменной окружения ADMIN_USER_IDS
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from uk_management_bot.database.session import SessionLocal
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.structured_logger import get_logger

logger = get_logger(__name__)


def init_admin_user() -> bool:
    """
    Инициализирует администратора из переменной окружения ADMIN_USER_IDS

    Returns:
        bool: True если администратор создан или уже существует, False в случае ошибки
    """
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")

    if not admin_ids_str:
        logger.warning("ADMIN_USER_IDS не задан в переменных окружения")
        return False

    # Получаем первый ID из списка (основной администратор)
    admin_ids = [id.strip() for id in admin_ids_str.split(",") if id.strip()]

    if not admin_ids:
        logger.warning("ADMIN_USER_IDS пустой после парсинга")
        return False

    main_admin_id = int(admin_ids[0])

    logger.info(f"Инициализация администратора с Telegram ID: {main_admin_id}")

    try:
        with SessionLocal() as session:
            # Проверяем, существует ли пользователь
            stmt = select(User).where(User.telegram_id == main_admin_id)
            existing_user = session.execute(stmt).scalar_one_or_none()

            if existing_user:
                # Проверяем, является ли пользователь администратором
                if "manager" in (existing_user.roles or ""):
                    logger.info(f"✅ Администратор уже существует: ID={existing_user.id}, "
                               f"Telegram ID={existing_user.telegram_id}, "
                               f"Username=@{existing_user.username or 'не задан'}")
                    return True
                else:
                    # Добавляем ВСЕ роли администратору
                    existing_user.roles = "applicant,executor,manager"
                    existing_user.role = "manager"  # Основная роль
                    existing_user.active_role = "manager"
                    existing_user.status = "active"

                    session.commit()
                    logger.info(f"✅ Роли администратора добавлены существующему пользователю: "
                               f"ID={existing_user.id}, Telegram ID={existing_user.telegram_id}")
                    return True

            # Создаем нового администратора с ВСЕМИ ролями
            admin_user = User(
                telegram_id=main_admin_id,
                username=f"admin_{main_admin_id}",  # Будет обновлено при первом сообщении
                first_name="Администратор",
                last_name="",
                role="manager",
                roles="applicant,executor,manager",  # ВСЕ роли для администратора
                active_role="manager",
                status="approved",  # ВАЖНО: approved для доступа к боту!
                language="ru",
                phone="+998000000000",  # Заглушка для телефона
                verification_status="approved"  # Администратор автоматически верифицирован
            )

            session.add(admin_user)
            session.commit()
            session.refresh(admin_user)

            logger.info(f"✅ Администратор создан успешно:")
            logger.info(f"   ID: {admin_user.id}")
            logger.info(f"   Telegram ID: {admin_user.telegram_id}")
            logger.info(f"   Роли: {admin_user.roles}")
            logger.info(f"   Статус: {admin_user.status}")
            logger.info(f"   Верификация: {admin_user.verification_status}")

            return True

    except Exception as e:
        logger.error(f"❌ Ошибка при создании администратора: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_all_admins() -> tuple[int, int]:
    """
    Инициализирует всех администраторов из ADMIN_USER_IDS

    Returns:
        tuple[int, int]: (количество созданных, количество обновленных)
    """
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")

    if not admin_ids_str:
        logger.warning("ADMIN_USER_IDS не задан в переменных окружения")
        return (0, 0)

    admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]

    if not admin_ids:
        logger.warning("ADMIN_USER_IDS пустой после парсинга")
        return (0, 0)

    logger.info(f"Инициализация {len(admin_ids)} администраторов: {admin_ids}")

    created_count = 0
    updated_count = 0

    try:
        with SessionLocal() as session:
            for admin_id in admin_ids:
                # Проверяем существование
                stmt = select(User).where(User.telegram_id == admin_id)
                existing_user = session.execute(stmt).scalar_one_or_none()

                if existing_user:
                    # Проверяем, есть ли уже все роли
                    current_roles = set((existing_user.roles or "").split(","))
                    required_roles = {"applicant", "executor", "manager"}

                    if not required_roles.issubset(current_roles) or existing_user.status != "approved":
                        # Обновляем на ВСЕ роли и правильный статус
                        existing_user.roles = "applicant,executor,manager"
                        existing_user.role = "manager"
                        existing_user.active_role = "manager"
                        existing_user.status = "approved"  # ВАЖНО: approved!
                        if not existing_user.phone:
                            existing_user.phone = "+998000000000"  # Заглушка

                        updated_count += 1
                        logger.info(f"✅ Обновлен администратор (добавлены все роли): Telegram ID={admin_id}")
                    else:
                        logger.info(f"✅ Администратор уже существует: ID={existing_user.id}, "
                                   f"Telegram ID={admin_id}, Username=@{existing_user.username or 'не задан'}, "
                                   f"Роли={existing_user.roles}")
                else:
                    # Создаем нового с ВСЕМИ ролями
                    admin_user = User(
                        telegram_id=admin_id,
                        username=f"admin_{admin_id}",
                        first_name="Администратор",
                        last_name="",
                        role="manager",
                        roles="applicant,executor,manager",  # ВСЕ роли
                        active_role="manager",
                        status="approved",  # ВАЖНО: approved!
                        language="ru",
                        phone="+998000000000",  # Заглушка для телефона
                        verification_status="approved"
                    )
                    session.add(admin_user)
                    created_count += 1
                    logger.info(f"✅ Создан администратор: Telegram ID={admin_id}")

            session.commit()

            logger.info(f"✅ Инициализация завершена: создано {created_count}, обновлено {updated_count}")
            return (created_count, updated_count)

    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации администраторов: {e}")
        import traceback
        traceback.print_exc()
        return (0, 0)


def main():
    """Главная функция для запуска из командной строки"""
    print("=" * 70)
    print("UK Management Bot - Инициализация администраторов")
    print("=" * 70)
    print()

    # Проверяем переменную окружения
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    if not admin_ids_str:
        print("❌ ОШИБКА: Переменная ADMIN_USER_IDS не задана!")
        print("   Установите её в .env файле:")
        print("   ADMIN_USER_IDS=123456789,987654321")
        return 1

    print(f"📋 ADMIN_USER_IDS: {admin_ids_str}")
    print()

    # Инициализируем всех администраторов
    created, updated = init_all_admins()

    print()
    print("=" * 70)
    if created > 0 or updated > 0:
        print(f"✅ УСПЕШНО:")
        print(f"   Создано администраторов: {created}")
        print(f"   Обновлено администраторов: {updated}")
        print("=" * 70)
        return 0
    else:
        print("⚠️  Администраторы не были созданы или обновлены")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
