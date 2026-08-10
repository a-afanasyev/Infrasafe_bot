"""Панель управления сотрудниками: главное меню, статистика, навигация.

AUD5-ARCH-3 (волна 1): перенос 1:1 из handlers/employee_management.py.
"""

import logging


from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db

from uk_management_bot.keyboards.employee_management import (
    get_employee_management_main_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router
from ._units import _load_employee_stats

logger = logging.getLogger(__name__)


# ═══ ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ СОТРУДНИКАМИ ═══

@router.callback_query(F.data == "employee_management_panel")
async def show_employee_management_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать панель управления сотрудниками"""
    logger.debug(f"Employee management panel called: callback_data={callback.data}")
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    logger.debug(f" has_access = {has_access}, roles = {roles}, user = {user}")
    
    if not has_access:
        logger.debug(f"Access denied for user {callback.from_user.id}")
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        logger.debug(" Начинаем получение статистики сотрудников")
        # Получаем статистику сотрудников
        stats = await run_db(_load_employee_stats, db=_db)
        logger.debug(f" Статистика получена: {stats}")
        
        # Показываем главное меню
        try:
            title = get_text('employee_management.main_title', language=lang)
            keyboard = get_employee_management_main_keyboard(stats, lang)
            logger.debug(f" Заголовок: {title}")
            logger.debug(" Клавиатура создана успешно")
            
            await callback.message.edit_text(
                title,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры: {e}")
            raise
        
        await callback.answer()
        logger.debug(" Панель управления сотрудниками успешно отображена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отображения панели управления сотрудниками: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "employee_mgmt_main")
async def back_to_main_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Вернуться к главному меню панели управления"""
    await show_employee_management_panel(callback, roles, active_role, user, _db=_db)


@router.callback_query(F.data == "employee_mgmt_stats")
async def show_employee_stats(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать статистику сотрудников"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        stats = await run_db(_load_employee_stats, db=_db)

        # Формируем текст статистики
        stats_text = f"📊 {get_text('employee_management.stats_title', language=lang)}\n\n"
        stats_text += f"📝 {get_text('employee_management.pending_employees', language=lang)}: {stats.get('pending', 0)}\n"
        stats_text += f"✅ {get_text('employee_management.active_employees', language=lang)}: {stats.get('active', 0)}\n"
        stats_text += f"🚫 {get_text('employee_management.blocked_employees', language=lang)}: {stats.get('blocked', 0)}\n"
        stats_text += f"🛠️ {get_text('employee_management.executors', language=lang)}: {stats.get('executors', 0)}\n"
        stats_text += f"👨‍💼 {get_text('employee_management.managers', language=lang)}: {stats.get('managers', 0)}\n"
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=get_employee_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения статистики сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ НАВИГАЦИЯ ═══

@router.callback_query(F.data == "no_action")
async def no_action_handler(callback: CallbackQuery, language: str = "ru"):
    """Обработчик для кнопок без действия"""
    await callback.answer()


@router.callback_query(F.data == "admin_panel")
async def back_to_admin_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться к админ панели"""
    lang = language
    
    try:
        from uk_management_bot.keyboards.admin import get_manager_main_keyboard
        
        await callback.message.edit_text(
            get_text('admin.panel_title', language=lang),
            reply_markup=get_manager_main_keyboard(language=lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к админ панели: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
