"""Списки сотрудников, карточка-действия и поиск.

AUD5-ARCH-3 (волна 1): перенос 1:1 из handlers/employee_management.py.
"""

import logging


from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db

from uk_management_bot.states.employee_management import EmployeeManagementStates
from uk_management_bot.keyboards.employee_management import (
    get_employee_list_keyboard,
    get_cancel_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router
from ._units import (
    _format_employee_name,
    _load_employees_page,
    _return_to_employee_info,
    _search_employees,
)

logger = logging.getLogger(__name__)


# ═══ СПИСКИ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("employee_mgmt_list_"))
async def show_employee_list(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать список сотрудников"""
    logger.debug(f" show_employee_list вызвана с callback_data: {callback.data}")
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
        # Парсим callback data
        parts = callback.data.split('_')
        list_type = parts[3]  # pending, active, blocked, executors, managers
        page = int(parts[4]) if len(parts) > 4 else 1
        
        logger.debug(f" Запрос списка сотрудников: тип={list_type}, страница={page}")

        employees_data = await run_db(lambda s: _load_employees_page(s, list_type, page), db=_db)

        logger.debug(f" Получены данные сотрудников: {len(employees_data.get('employees', []))} сотрудников")
        
        # Формируем заголовок
        title_map = {
            'pending': get_text('employee_management.pending_employees', language=lang),
            'active': get_text('employee_management.active_employees', language=lang),
            'blocked': get_text('employee_management.blocked_employees', language=lang),
            'executors': get_text('employee_management.executors', language=lang),
            'managers': get_text('employee_management.managers', language=lang)
        }
        
        title = f"👥 {title_map.get(list_type, list_type)}"
        
        await callback.message.edit_text(
            title,
            reply_markup=get_employee_list_keyboard(employees_data, list_type, lang)
        )
        
        await callback.answer()
        logger.debug(" Список сотрудников успешно отображен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отображения списка сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ДЕЙСТВИЯ С СОТРУДНИКАМИ ═══

@router.callback_query(F.data.startswith("employee_mgmt_employee_"))
async def show_employee_actions(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать действия с сотрудником"""
    logger.debug(f" show_employee_actions вызвана с callback_data: {callback.data}")
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
        # Получаем ID сотрудника
        employee_id = int(callback.data.split('_')[3])
        logger.debug(f" Запрошен сотрудник с ID: {employee_id}")

        # AUD5-CODE-8: карточка рендерится единственным хелпером
        # _return_to_employee_info — раньше здесь была вторая копия того же
        # текста. Вместе с копией ушёл fallback на deprecated employee.role:
        # роли живут в employee.roles (см. CLAUDE.md, «Роли в БД»).
        rendered = await _return_to_employee_info(callback, employee_id, lang, _db=_db)
        if rendered:
            await callback.answer()
        else:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отображения действий с сотрудником: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ПОИСК СОТРУДНИКОВ ═══

@router.callback_query(F.data == "employee_mgmt_search")
async def start_employee_search(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Начать поиск сотрудников"""
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
        await callback.message.edit_text(
            get_text('employee_management.search_instructions', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )

        # BUG-BOT-025: переводим пользователя в FSM-состояние ожидания запроса,
        # иначе message-handler ниже не сработает.
        await state.set_state(EmployeeManagementStates.waiting_for_search_query)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала поиска сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(EmployeeManagementStates.waiting_for_search_query)
async def handle_employee_search_query(message: Message, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """BUG-BOT-025: обработка введённого запроса поиска сотрудников.

    Ищем по first_name / last_name / username / phone (ILIKE %query%).
    На пусто-результат возвращаем дружелюбное сообщение, иначе — inline-клавиатуру
    с кнопками-сотрудниками.
    """
    lang = language

    # Проверяем права доступа (тот же check, что и на старте)
    if not has_admin_access(roles=roles, user=user):
        await message.answer(get_text('errors.permission_denied', language=lang))
        await state.clear()
        return

    raw_query = (message.text or "").strip()
    if not raw_query:
        await message.answer(get_text('employee_management.search_empty_query', language=lang))
        return

    try:
        employees = await run_db(lambda s: _search_employees(s, raw_query), db=_db)

        if not employees:
            await message.answer(
                get_text('employee_management.search_not_found', language=lang),
                reply_markup=get_cancel_keyboard(lang)
            )
            await state.clear()
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = []
        for emp in employees:
            label = _format_employee_name(emp)
            rows.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"employee_view_{emp.id}"
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text=get_text('buttons.cancel', language=lang),
                callback_data="employee_management_panel"
            )
        ])

        await message.answer(
            get_text('employee_management.search_results_header', language=lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка поиска сотрудников: {e}")
        await message.answer(get_text('errors.unknown_error', language=lang))
        await state.clear()
