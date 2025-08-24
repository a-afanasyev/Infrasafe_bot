from typing import Any, Dict, Optional
import json
import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import get_user_roles, get_active_role

from aiogram.types import Message, CallbackQuery

from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)


async def auth_middleware(handler, event: Any, data: Dict[str, Any]):
    """Загружает пользователя по telegram_id и подготавливает базовый контекст аутентификации.

    В data устанавливает:
    - data["user"]: объект User или None
    - data["user_status"]: строка статуса (pending|approved|blocked) или None

    Блокировка:
    - Если статус пользователя 'blocked' — формируем мягкий ответ и останавливаем обработку.

    Fail-safe поведение:
    - При любых ошибках возвращаем безопасные дефолты и НЕ падаем, чтобы не блокировать обработчики.
    """
    telegram_id: Optional[int] = None

    try:
        # В aiogram 3.x middleware работает с Update объектами
        from aiogram.types import Update
        
        if isinstance(event, Update):
            # Извлекаем telegram_id из message или callback_query
            if event.message:
                telegram_id = event.message.from_user.id if event.message.from_user else None
            elif event.callback_query:
                telegram_id = event.callback_query.from_user.id if event.callback_query.from_user else None
            else:
                telegram_id = None
        elif isinstance(event, Message):
            telegram_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id if event.from_user else None
        else:
            # Неизвестный тип события — пропускаем без аутентификации
            data["user"] = None
            data["user_status"] = None
            return await handler(event, data)
    except Exception:
        data["user"] = None
        data["user_status"] = None
        return await handler(event, data)

    db = data.get("db")
    if db is None or telegram_id is None:
        data["user"] = None
        data["user_status"] = None
        return await handler(event, data)

    try:
        user: Optional[User] = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        data["user"] = user
        data["user_status"] = getattr(user, "status", None) if user else None
        


        if user and user.status == "blocked":
            # Мягкая блокировка: локализованное сообщение и ранний выход
            try:
                language = None
                try:
                    if isinstance(event, Message):
                        language = getattr(event.from_user, "language_code", None)
                    elif isinstance(event, CallbackQuery):
                        language = getattr(event.from_user, "language_code", None)
                except Exception:
                    language = None
                text = get_text("auth.blocked", language=language or "ru")
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                # Не зовем handler — ранний выход
                return None
            except Exception as send_err:
                logger.warning(f"Не удалось отправить сообщение о блокировке: {send_err}")
                return None

    except Exception as exc:
        logger.warning(f"auth_middleware: ошибка загрузки пользователя: {exc}")
        data["user"] = None
        data["user_status"] = None

    return await handler(event, data)


async def role_mode_middleware(handler, event: Any, data: Dict[str, Any]):
    """Формирует контекст ролей и активного режима пользователя.

    В data устанавливает:
    - data["roles"]: список ролей пользователя (str)
    - data["active_role"]: текущая активная роль (str)

    Источники данных:
    - User.roles — JSON-строка с массивом ролей
    - User.active_role — строка
    - Для обратной совместимости, если roles пусто — берём из User.role

    Fail-safe: на любые ошибки парсинга — дефолты roles=["applicant"], active_role="applicant".
    """
    user: Optional[User] = data.get("user")

    # Используем утилитарные функции для получения ролей
    if user:
        roles_list = get_user_roles(user)
        active_role = get_active_role(user)
        # ОТЛАДКА для пользователя с Telegram ID 48617336
        if user.telegram_id == 48617336:
            print(f"🔍 MIDDLEWARE DEBUG: user.telegram_id={user.telegram_id}")
            print(f"🔍 MIDDLEWARE DEBUG: user.role={user.role}")
            print(f"🔍 MIDDLEWARE DEBUG: user.roles={user.roles}")
            print(f"🔍 MIDDLEWARE DEBUG: user.active_role={user.active_role}")
            print(f"🔍 MIDDLEWARE DEBUG: roles_list={roles_list}")
            print(f"🔍 MIDDLEWARE DEBUG: active_role={active_role}")
    else:
        roles_list = ["applicant"]
        active_role = "applicant"

    data["roles"] = roles_list
    data["active_role"] = active_role

    return await handler(event, data)

