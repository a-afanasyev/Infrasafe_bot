"""Редактирование сотрудника: вход в меню и телефон.

AUD5-ARCH-3 (волна 1): перенос 1:1 из handlers/employee_management.py.

ФИО отсюда ушло в `handlers/user_rename.py` — общий флоу с карточкой жителя:
поле одно, а писателей было два, и они разошлись (здесь ФИО писалось без
валидации и без аудита). Кнопка «📝 ФИО» в `get_employee_edit_keyboard` теперь
шлёт `rename_user_emp_<id>`, а прежний `edit_employee_name_<id>` живёт там же
как legacy-вход для клавиатур, уже отрисованных в чатах.
"""

import logging


from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db

from uk_management_bot.states.employee_management import EmployeeManagementStates
from uk_management_bot.keyboards.employee_management import (
    get_cancel_keyboard,
    get_employee_edit_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router
from ._units import (
    _format_employee_name,
    _load_employee,
    _update_employee_phone,
)

logger = logging.getLogger(__name__)


# ═══ РЕДАКТИРОВАНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.regexp(r"^edit_employee_\d+$"))
async def edit_employee_entry(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """MGR-03: вход в редактирование сотрудника (кнопка `edit_employee_<id>`).

    Раньше кнопка была no-op — листовые `edit_employee_name_`/`edit_employee_phone_`
    есть, а входного хендлера не было. Строгий regex `^edit_employee_\\d+$` не
    перехватывает листовые (после id у них идёт `_name_`/`_phone_`).
    """
    lang = language

    # Проверяем права доступа (как в листовых хендлерах)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return

    try:
        employee_id = int(callback.data.split('_')[2])

        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)
        if not employee:
            await callback.answer(get_text('errors.user_not_found', language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("employee_mgmt.handlers.edit_menu", language=lang).format(
                employee_name=_format_employee_name(employee)
            ),
            reply_markup=get_employee_edit_keyboard(employee_id, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка открытия меню редактирования сотрудника: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("edit_employee_phone_"))
async def edit_employee_phone(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Редактировать телефон сотрудника"""
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
        employee_id = int(callback.data.split('_')[3])

        # Получаем сотрудника
        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)

        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'action': 'edit_phone'
        })
        
        await state.set_state(EmployeeManagementStates.editing_phone)
        
        # Запрашиваем новый телефон
        await callback.message.edit_text(
            get_text("employee_mgmt.handlers.enter_new_phone", language=lang).format(
                employee_name=_format_employee_name(employee),
                current_phone=employee.phone or get_text("employee_mgmt.handlers.not_specified", language=lang)
            ),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования телефона сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(EmployeeManagementStates.editing_phone)
async def process_employee_phone_edit(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать изменение телефона сотрудника"""
    try:
        new_phone = message.text.strip()
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        if not new_phone:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.phone_cannot_be_empty", language=lang))
            return

        # Обновляем телефон
        updated = await run_db(lambda s: _update_employee_phone(s, target_employee_id, new_phone), db=_db)
        if updated:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.phone_updated", language=lang).format(phone=new_phone))
        else:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.employee_not_found", language=lang))

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обработки изменения телефона: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_phone", language=lang))
        await state.clear()
