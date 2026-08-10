"""Роли и специализации сотрудников: смена наборов, toggle/save/cancel, комментарии.

AUD5-ARCH-3 (волна 1): перенос 1:1 из handlers/employee_management.py.
"""

import logging


from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db

from uk_management_bot.states.employee_management import EmployeeManagementStates
from uk_management_bot.keyboards.employee_management import (
    get_cancel_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access, parse_roles_safe
from uk_management_bot.utils.specializations import parse_specializations
from uk_management_bot.database.models.user import User

from ._router import router
from ._units import (
    _apply_role_change,
    _apply_specialization_change,
    _format_employee_name,
    _load_detailed_spec_stats,
    _load_employee,
    _return_to_employee_info,
)

logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("change_employee_role_"))
async def change_employee_role(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Изменить роль сотрудника"""
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

        # Получаем текущие роли (COD-01: канонический парсер, JSON+CSV)
        user_roles = parse_roles_safe(employee.roles)
        
        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'original_roles': user_roles.copy(),
            'current_roles': user_roles.copy()
        })
        
        await state.set_state(EmployeeManagementStates.selecting_roles)
        
        # Формируем сообщение
        user_name = _format_employee_name(employee)
        message_text = f"🎯 {get_text('employee_management.change_role', language=lang)}: {user_name}\n\n"
        no_roles_text = get_text("employee_mgmt.handlers.no_roles", language=lang)
        # MGR-06: локализуем роли через канон-helper (roles.* namespace) вместо
        # сырых DB-значений ('executor' → 'Исполнитель').
        from uk_management_bot.utils.employee_display import format_roles
        message_text += get_text("employee_mgmt.handlers.current_roles", language=lang).format(
            roles=format_roles(user_roles, lang) if user_roles else no_roles_text
        )
        
        # Показываем меню выбора ролей
        from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_roles_management_keyboard(user_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения роли сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ СПЕЦИАЛИЗАЦИИ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("change_employee_specialization_"))
async def change_employee_specialization(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Изменить специализацию сотрудника"""
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

        # AUD5-CODE-8: единый парсер вместо локальной копии — та делала
        # json.loads без гейта startswith('['), поэтому JSON-скаляр ('123')
        # превращался в int и ронял хендлер на .copy(), а элементы
        # JSON-списка не чистились от пробелов/пустых значений.
        user_specializations = sorted(parse_specializations(employee))
        
        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'original_specializations': user_specializations.copy(),
            'current_specializations': user_specializations.copy()
        })
        
        await state.set_state(EmployeeManagementStates.selecting_specializations)
        
        # Формируем сообщение
        user_name = _format_employee_name(employee)
        message_text = f"🛠️ {get_text('employee_management.specialization', language=lang)}: {user_name}\n\n"
        message_text += f"{get_text('specializations.current_specializations', language=lang)}: "
        
        # Форматируем специализации
        if user_specializations:
            spec_names = []
            for spec in user_specializations:
                spec_text = get_text(f'specializations.{spec}', language=lang, default=spec)
                spec_names.append(spec_text)
            message_text += ", ".join(spec_names)
        else:
            message_text += get_text("employee_mgmt.handlers.no_specializations", language=lang)
        
        # Показываем меню выбора специализаций
        from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_specializations_selection_keyboard(user_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения специализации сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ СПЕЦИАЛИЗАЦИЯМИ ═══

@router.callback_query(F.data == "employee_mgmt_specializations")
async def show_employee_specializations_management(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать управление специализациями сотрудников"""
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
        # Получаем детальную статистику по специализациям
        detailed_stats = await run_db(_load_detailed_spec_stats, db=_db)

        # Формируем сообщение со статистикой и списком сотрудников
        message_text = get_text("employee_mgmt.handlers.specialization_stats_title", language=lang) + "\n\n"
        
        if detailed_stats:
            for spec_key, spec_data in detailed_stats.items():
                # Переводим название специализации
                spec_name = get_text(f'specializations.{spec_key}', language=lang)
                count = spec_data['count']
                employees = spec_data['employees']
                
                message_text += get_text("employee_mgmt.handlers.spec_employee_count", language=lang).format(spec_name=spec_name, count=count) + "\n"
                
                # Добавляем список сотрудников
                if employees:
                    for employee in employees:
                        # AUD5-CODE-8: имя через канон вместо инлайн-копии
                        message_text += f"  - {_format_employee_name(employee)}\n"
                else:
                    message_text += f"  - {get_text('employee_mgmt.handlers.no_employees', language=lang)}\n"
                
                message_text += "\n"
        else:
            message_text += get_text("employee_mgmt.handlers.no_specialization_data", language=lang) + "\n"
        
        message_text += get_text("employee_mgmt.handlers.specialization_management_hint", language=lang)
        
        # Кнопка "Назад"
        from uk_management_bot.keyboards.employee_management import get_cancel_keyboard
        await callback.message.edit_text(
            message_text,
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения управления специализациями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ВЫБОР РОЛЕЙ И СПЕЦИАЛИЗАЦИЙ ═══

@router.callback_query(F.data.startswith("role_toggle_"), EmployeeManagementStates.selecting_roles)
async def toggle_role(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Переключить роль"""
    try:
        role = callback.data.split('_')[-1]
        data = await state.get_data()
        current_roles = data.get('current_roles', [])
        
        if role in current_roles:
            current_roles.remove(role)
        else:
            current_roles.append(role)
        
        await state.update_data(current_roles=current_roles)
        
        # Обновляем клавиатуру
        from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
        lang = language
        
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения роли: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "role_save", EmployeeManagementStates.selecting_roles)
async def save_employee_roles(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить роли сотрудника"""
    try:
        data = await state.get_data()
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        
        # Проверяем, изменились ли роли
        if set(original_roles) == set(current_roles):
            lang = language
            await callback.answer(get_text("employee_mgmt.handlers.roles_not_changed", language=lang), show_alert=True)
            await state.clear()
            return
        
        # Запрашиваем комментарий
        await state.update_data({'action': 'roles_change'})
        await state.set_state(EmployeeManagementStates.waiting_for_role_comment)
        
        lang = language
        await callback.message.edit_text(
            get_text('moderation.enter_role_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения ролей: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "role_cancel", EmployeeManagementStates.selecting_roles)
async def cancel_roles_editing(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Отменить редактирование ролей"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        await state.clear()

        # Возвращаемся к информации о сотруднике (render-only helper не отвечает
        # на callback — отвечаем здесь ровно один раз).
        rendered = await _return_to_employee_info(callback, target_employee_id, language, _db=_db)
        if rendered:
            await callback.answer()
        else:
            await callback.answer(get_text('errors.user_not_found', language=language), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отмены редактирования ролей: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.message(EmployeeManagementStates.waiting_for_role_comment)
async def process_role_change_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать комментарий для изменения ролей"""
    try:
        comment = message.text
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        current_roles = data.get('current_roles', [])

        # Запрет снятия последней роли (паритет с AuthService.remove_role):
        # roles=[] недопустимо — у пользователя всегда должна быть хотя бы одна роль.
        if not current_roles:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.cannot_remove_last_role", language=lang))
            await state.clear()
            return

        logger.debug(f" Обработка комментария ролей. target_employee_id={target_employee_id}, current_roles={current_roles}")

        outcome = await run_db(
            lambda s: _apply_role_change(
                s, message.from_user.id, target_employee_id, current_roles, comment),
            db=_db)
        if outcome == "no_actor":
            logger.error(f"User not found: telegram_id={message.from_user.id}")
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.user_not_found_error", language=lang))
            await state.clear()
            return
        if outcome == "no_target":
            logger.error(f"Employee not found: ID {target_employee_id}")
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.employee_not_found", language=lang))
            await state.clear()
            return

        logger.debug(" Роли успешно обновлены и сохранены")
        await state.clear()

        lang = language
        no_roles_text = get_text("employee_mgmt.handlers.no_roles", language=lang)
        await message.answer(
            get_text("employee_mgmt.handlers.roles_updated", language=lang).format(
                roles=', '.join(current_roles) if current_roles else no_roles_text
            )
        )

    except Exception as e:
        logger.error(f"Error processing role change comment: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_roles", language=lang))
        await state.clear()


@router.callback_query(F.data.startswith("spec_toggle_"), EmployeeManagementStates.selecting_specializations)
async def toggle_specialization(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Переключить специализацию"""
    try:
        specialization = callback.data.split('_')[-1]
        data = await state.get_data()
        current_specializations = data.get('current_specializations', [])
        
        if specialization in current_specializations:
            current_specializations.remove(specialization)
        else:
            current_specializations.append(specialization)
        
        await state.update_data(current_specializations=current_specializations)
        
        # Обновляем клавиатуру
        from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
        lang = language
        
        await callback.message.edit_reply_markup(
            reply_markup=get_specializations_selection_keyboard(current_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "spec_save", EmployeeManagementStates.selecting_specializations)
async def save_employee_specializations(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить специализации сотрудника"""
    try:
        data = await state.get_data()
        original_specializations = data.get('original_specializations', [])
        current_specializations = data.get('current_specializations', [])
        
        # Проверяем, изменились ли специализации
        if set(original_specializations) == set(current_specializations):
            lang = language
            await callback.answer(get_text("employee_mgmt.handlers.specializations_not_changed", language=lang), show_alert=True)
            await state.clear()
            return
        
        # Запрашиваем комментарий
        await state.update_data({'action': 'specializations_change'})
        await state.set_state(EmployeeManagementStates.waiting_for_specialization_comment)
        
        lang = language
        await callback.message.edit_text(
            get_text('moderation.enter_specialization_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "spec_cancel", EmployeeManagementStates.selecting_specializations)
async def cancel_specializations_editing(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Отменить редактирование специализаций"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        await state.clear()

        # Возвращаемся к информации о сотруднике (render-only helper не отвечает
        # на callback — отвечаем здесь ровно один раз).
        rendered = await _return_to_employee_info(callback, target_employee_id, language, _db=_db)
        if rendered:
            await callback.answer()
        else:
            await callback.answer(get_text('errors.user_not_found', language=language), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отмены редактирования специализаций: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.message(EmployeeManagementStates.waiting_for_specialization_comment)
async def process_specialization_change_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать комментарий для изменения специализаций"""
    try:
        comment = message.text
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        current_specializations = data.get('current_specializations', [])

        outcome = await run_db(
            lambda s: _apply_specialization_change(
                s, message.from_user.id, target_employee_id, current_specializations, comment),
            db=_db)
        if outcome == "no_actor":
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.user_not_found_error", language=lang))
            await state.clear()
            return

        await state.clear()

        if outcome == "ok":
            lang = language
            no_specs_text = get_text("employee_mgmt.handlers.no_specializations", language=lang)
            await message.answer(
                get_text("employee_mgmt.handlers.specializations_updated", language=lang).format(
                    specializations=', '.join(current_specializations) if current_specializations else no_specs_text
                )
            )
        else:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.error_saving_specializations", language=lang))

    except Exception as e:
        logger.error(f"Ошибка обработки комментария специализаций: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_specializations", language=lang))
        await state.clear()
