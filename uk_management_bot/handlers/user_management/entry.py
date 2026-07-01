"""Интеграция панели управления пользователями с админ-панелью."""
import logging

from aiogram.types import Message
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)


# ═══ ИНТЕГРАЦИЯ С АДМИН ПАНЕЛЬЮ ═══

async def open_user_management(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Открыть панель управления пользователями (для интеграции с админ панелью)"""
    lang = language
    
    try:
        # Получаем статистику пользователей
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        # Показываем главное меню
        await message.answer(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отображения панели управления пользователями: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )


# admin_panel callback handler is in employee_management.py (uses edit_text)
