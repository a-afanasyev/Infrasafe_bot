from typing import Any, Dict, Optional, List
import inspect
import logging
from functools import wraps
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
    except Exception as e:
        # CODE-11: не глотать молча — debug-лог для расследований.
        logger.debug(f"auth-middleware: не удалось извлечь telegram_id из события {type(event).__name__}: {e}")
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
        # Логирование для отладки (только в debug режиме)
        logger.debug(f"User roles processed: telegram_id={user.telegram_id}, roles={roles_list}, active_role={active_role}")
    else:
        roles_list = ["applicant"]
        active_role = "applicant"

    data["roles"] = roles_list
    data["active_role"] = active_role
    
    # Debug: посмотрим что передаём дальше
    logger.debug(f"role_mode_middleware: передаём данные data.keys()={list(data.keys())}, roles={roles_list}, active_role={active_role}")

    return await handler(event, data)


def require_role(required_roles: List[str]):
    """Декоратор для проверки ролей пользователя перед выполнением хэндлера.
    
    Args:
        required_roles: Список ролей, одна из которых должна быть у пользователя
    
    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Debug: посмотрим что приходит
            logger.debug(f"require_role debug: args={len(args)}, kwargs_keys={list(kwargs.keys())}")
            
            # Получаем event (первый аргумент или из kwargs)
            event = args[0] if args else kwargs.get("event")
            
            # Получаем db из kwargs или извлекаем из контекста
            db = kwargs.get("db")
            if not db and event:
                # Пытаемся получить db из контекста события
                try:
                    from aiogram import Bot
                    bot = Bot.get_current()
                    if bot and hasattr(bot, '_dispatcher'):
                        # Получаем db из dispatcher context
                        pass  # Это сложно, лучше получить из kwargs или БД напрямую
                except Exception:
                    pass
            
            # Получаем telegram_id из event
            telegram_id = None
            if event:
                if hasattr(event, 'from_user') and event.from_user:
                    telegram_id = event.from_user.id
            
            # Получаем роли из kwargs (aiogram 3 DI) или из БД
            user_roles = kwargs.get("roles", [])
            user = kwargs.get("user")
            
            # Если роли не получены через DI, получаем их из БД (db from middleware DI)
            if not user_roles and telegram_id and db:
                try:
                    from uk_management_bot.database.models.user import User as _User
                    user = db.query(_User).filter(_User.telegram_id == telegram_id).first()
                    if user:
                        from uk_management_bot.utils.auth_helpers import get_user_roles as _get_user_roles
                        user_roles = _get_user_roles(user)
                        logger.debug(f"require_role: получили роли из БД: {user_roles}")
                except Exception as e:
                    logger.warning(f"Ошибка получения ролей из БД: {e}")
            
            logger.debug(f"require_role check: user_roles={user_roles}, required_roles={required_roles}, user={user}")
            
            # Проверяем права доступа
            has_access = False
            if user_roles:
                has_access = any(role in user_roles for role in required_roles)
            else:
                logger.warning(f"require_role: user_roles пустой! kwargs={list(kwargs.keys())}, event={type(event).__name__ if event else None}, telegram_id={telegram_id}")
            
            if not has_access:
                logger.warning(f"Access denied for user {user.telegram_id if user else telegram_id or 'unknown'}: has roles {user_roles}, needs {required_roles}")
                
                # Формируем сообщение об отсутствии прав
                language = None
                if event and hasattr(event, 'from_user') and event.from_user:
                    language = getattr(event.from_user, "language_code", "ru")
                
                # Пытаемся получить язык из БД
                if not language and telegram_id and db:
                    try:
                        from uk_management_bot.utils.helpers import get_user_language
                        language = get_user_language(telegram_id, db)
                    except Exception:
                        pass
                
                text = get_text("auth.no_access", language=language or "ru")
                
                try:
                    if isinstance(event, Message):
                        await event.answer(text)
                    elif isinstance(event, CallbackQuery):
                        await event.answer(text, show_alert=True)
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение об отсутствии прав: {e}")
                
                return None
            
            logger.debug(f"Access granted for user {user.telegram_id if user else telegram_id or 'unknown'}")
            
            # Если права есть, выполняем хэндлер
            return await func(*args, **kwargs)
        
        # Defensive: explicitly copy __signature__ so aiogram DI sees
        # the original parameter names even if __wrapped__ handling changes.
        wrapper.__signature__ = inspect.signature(func)
        return wrapper
    return decorator

