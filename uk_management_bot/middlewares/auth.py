from typing import Any, Dict, Optional
import json
import logging
from utils.helpers import get_text

from aiogram.types import Message, CallbackQuery

from database.models.user import User

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
        if isinstance(event, Message):
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
        user: Optional[User] = db.query(User).filter(User.telegram_id == telegram_id).one_or_none()
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
                return
            except Exception as send_err:
                logger.warning(f"Не удалось отправить сообщение о блокировке: {send_err}")
                return

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

    # Дефолты
    roles_list = ["applicant"]
    active_role = "applicant"

    try:
        if user:
            # Разбираем список ролей
            if getattr(user, "roles", None):
                try:
                    parsed = json.loads(user.roles)
                    if isinstance(parsed, list) and parsed:
                        roles_list = [str(r) for r in parsed if isinstance(r, str)] or roles_list
                except Exception as parse_exc:
                    logger.warning(f"role_mode_middleware: ошибка парсинга roles: {parse_exc}")
            elif getattr(user, "role", None):
                # Обратная совместимость
                roles_list = [user.role]

            # Активная роль
            if getattr(user, "active_role", None):
                active_role = user.active_role
            else:
                active_role = roles_list[0] if roles_list else "applicant"

            # Нормализация: активная роль должна входить в список ролей
            if active_role not in roles_list:
                active_role = roles_list[0] if roles_list else "applicant"
    except Exception as exc:
        logger.warning(f"role_mode_middleware: ошибка обработки ролей: {exc}")

    data["roles"] = roles_list
    data["active_role"] = active_role

    return await handler(event, data)

