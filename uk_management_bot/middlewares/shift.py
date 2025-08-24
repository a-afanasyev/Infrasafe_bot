from typing import Any, Dict, Optional

from aiogram.types import Message, CallbackQuery

from uk_management_bot.services.shift_service import ShiftService


async def shift_context_middleware(handler, event: Any, data: Dict[str, Any]):
    """Проставляет в data информацию о смене текущего пользователя.

    data["shift_context"] = {
        "is_active": bool,
        "shift": Optional[object],
    }
    """
    telegram_id: Optional[int] = None

    # Извлекаем telegram_id из события
    try:
        if isinstance(event, Message):
            telegram_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id if event.from_user else None
        else:
            # Неизвестный тип события — оставляем контекст по умолчанию
            data["shift_context"] = {"is_active": False, "shift": None}
            return await handler(event, data)
    except Exception:
        data["shift_context"] = {"is_active": False, "shift": None}
        return await handler(event, data)

    # Получаем доступ к БД из ранее установленного middleware
    db = data.get("db")
    if db is None or telegram_id is None:
        data["shift_context"] = {"is_active": False, "shift": None}
        return await handler(event, data)

    try:
        service = ShiftService(db)
        # Одна выборка из БД: получаем активную смену, булево состояние выводим из факта наличия
        shift = service.get_active_shift(telegram_id)
        is_active = bool(shift)
        data["shift_context"] = {"is_active": is_active, "shift": shift}
    except Exception:
        # Fail-safe: не блокируем обработку при ошибках контекста
        data["shift_context"] = {"is_active": False, "shift": None}

    return await handler(event, data)


