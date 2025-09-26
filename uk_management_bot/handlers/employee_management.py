"""
Обработчики для управления сотрудниками

Содержит обработчики для:
- Панели управления сотрудниками
- Списков и поиска сотрудников
- Действий модерации
- Управления ролями и специализациями
"""

import logging
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.states.employee_management import EmployeeManagementStates
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import text
import json
from datetime import datetime

def _format_employee_name(employee) -> str:
    """Форматирует имя сотрудника для отображения"""
    if employee.first_name and employee.last_name:
        return f"{employee.first_name} {employee.last_name}"
    elif employee.first_name:
        return employee.first_name
    elif employee.username:
        return f"@{employee.username}"
    else:
        return f"ID: {employee.telegram_id}"


async def _return_to_employee_info(callback: CallbackQuery, db: Session, employee_id: int):
    """Вернуться к информации о сотруднике (без проверки прав)"""
    try:
        lang = callback.from_user.language_code or 'ru'
        
        # Получаем сотрудника
        user_mgmt_service = UserManagementService(db)
        employee = user_mgmt_service.get_user_by_id(employee_id)
        
        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Формируем информацию о сотруднике
        employee_info = f"👤 {get_text('employee_management.employee_info', language=lang)}\n\n"
        
        # Формируем имя из доступных полей
        if employee.first_name and employee.last_name:
            full_name = f"{employee.first_name} {employee.last_name}"
        elif employee.first_name:
            full_name = employee.first_name
        elif employee.username:
            full_name = f"@{employee.username}"
        else:
            full_name = f"ID: {employee.telegram_id}"
            
        employee_info += f"📝 {get_text('employee_management.full_name', language=lang)}: {full_name}\n"
        employee_info += f"📱 {get_text('employee_management.phone', language=lang)}: {employee.phone or 'Не указано'}\n"
        employee_info += f"🎯 {get_text('employee_management.role', language=lang)}: {employee.role or 'Не указано'}\n"
        employee_info += f"📊 {get_text('employee_management.status', language=lang)}: {employee.status or 'Не указано'}\n"
        
        if employee.specialization:
            employee_info += f"🛠️ {get_text('employee_management.specialization', language=lang)}: {employee.specialization}\n"
        
        employee_info += f"📅 {get_text('employee_management.created_at', language=lang)}: {employee.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        await callback.message.edit_text(
            employee_info,
            reply_markup=get_employee_actions_keyboard(employee_id, employee.status, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к информации о сотруднике: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
from uk_management_bot.keyboards.employee_management import (
    get_employee_management_main_keyboard,
    get_employee_list_keyboard,
    get_employee_actions_keyboard,
    get_roles_management_keyboard,
    get_specializations_selection_keyboard,
    get_cancel_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.states.employee_management import EmployeeManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)
router = Router()


# ═══ ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ СОТРУДНИКАМИ ═══

@router.callback_query(F.data == "employee_management_panel")
async def show_employee_management_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать панель управления сотрудниками"""
    logger.debug(f"Employee management panel called: callback_data={callback.data}")
    lang = callback.from_user.language_code or 'ru'
    
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
        logger.debug(f" Начинаем получение статистики сотрудников")
        # Получаем статистику сотрудников
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_employee_stats()
        logger.debug(f" Статистика получена: {stats}")
        
        # Показываем главное меню
        try:
            title = get_text('employee_management.main_title', language=lang)
            keyboard = get_employee_management_main_keyboard(stats, lang)
            logger.debug(f" Заголовок: {title}")
            logger.debug(f" Клавиатура создана успешно")
            
            await callback.message.edit_text(
                title,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры: {e}")
            raise
        
        await callback.answer()
        logger.debug(f" Панель управления сотрудниками успешно отображена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отображения панели управления сотрудниками: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "employee_mgmt_main")
async def back_to_main_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Вернуться к главному меню панели управления"""
    await show_employee_management_panel(callback, db, roles, active_role, user)


@router.callback_query(F.data == "employee_mgmt_stats")
async def show_employee_stats(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать статистику сотрудников"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_employee_stats()
        
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


# ═══ СПИСКИ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("employee_mgmt_list_"))
async def show_employee_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать список сотрудников"""
    logger.debug(f" show_employee_list вызвана с callback_data: {callback.data}")
    lang = callback.from_user.language_code or 'ru'
    
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
        
        user_mgmt_service = UserManagementService(db)
        employees_data = user_mgmt_service.get_employees_list(list_type, page)
        
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
        logger.debug(f" Список сотрудников успешно отображен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отображения списка сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ДЕЙСТВИЯ С СОТРУДНИКАМИ ═══

@router.callback_query(F.data.startswith("employee_mgmt_employee_"))
async def show_employee_actions(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать действия с сотрудником"""
    logger.debug(f" show_employee_actions вызвана с callback_data: {callback.data}")
    lang = callback.from_user.language_code or 'ru'
    
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
        
        user_mgmt_service = UserManagementService(db)
        employee = user_mgmt_service.get_user_by_id(employee_id)
        logger.debug(f" Сотрудник найден: {employee}")
        
        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Формируем информацию о сотруднике
        employee_info = f"👤 {get_text('employee_management.employee_info', language=lang)}\n\n"
        
        # Формируем имя из доступных полей
        if employee.first_name and employee.last_name:
            full_name = f"{employee.first_name} {employee.last_name}"
        elif employee.first_name:
            full_name = employee.first_name
        elif employee.username:
            full_name = f"@{employee.username}"
        else:
            full_name = f"ID: {employee.telegram_id}"
            
        employee_info += f"📝 {get_text('employee_management.full_name', language=lang)}: {full_name}\n"
        employee_info += f"📱 {get_text('employee_management.phone', language=lang)}: {employee.phone or 'Не указано'}\n"
        
        # Отображаем все роли пользователя
        if employee.roles:
            try:
                user_roles = json.loads(employee.roles)
                if user_roles:
                    roles_text = ", ".join(user_roles)
                    employee_info += f"🎯 {get_text('employee_management.role', language=lang)}: {roles_text}\n"
                else:
                    employee_info += f"🎯 {get_text('employee_management.role', language=lang)}: Не указано\n"
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга ролей сотрудника {employee.id}: {e}")
                employee_info += f"🎯 {get_text('employee_management.role', language=lang)}: {employee.role or 'Не указано'}\n"
        else:
            employee_info += f"🎯 {get_text('employee_management.role', language=lang)}: {employee.role or 'Не указано'}\n"
        
        employee_info += f"📊 {get_text('employee_management.status', language=lang)}: {employee.status or 'Не указано'}\n"
        
        if employee.specialization:
            employee_info += f"🛠️ {get_text('employee_management.specialization', language=lang)}: {employee.specialization}\n"
        
        employee_info += f"📅 {get_text('employee_management.created_at', language=lang)}: {employee.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        await callback.message.edit_text(
            employee_info,
            reply_markup=get_employee_actions_keyboard(employee_id, employee.status, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения действий с сотрудником: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОДОБРЕНИЕ/ОТКЛОНЕНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("approve_employee_"))
async def approve_employee(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Одобрить сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])
        
        # Получаем ID пользователя из базы данных по telegram_id
        current_user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not current_user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        auth_service = AuthService(db)
        success = auth_service.approve_user(employee_id, current_user.id, "Одобрен через панель управления сотрудниками")
        
        if success:
            await callback.answer(
                get_text('employee_management.employee_approved', language=lang),
                show_alert=True
            )
            
            # Возвращаемся к списку
            await show_employee_list(callback, db, roles, active_role, user)
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка одобрения сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("reject_employee_"))
async def reject_employee(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Отклонить сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])
        
        # Получаем ID пользователя из базы данных по telegram_id
        current_user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not current_user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        auth_service = AuthService(db)
        success = auth_service.block_user(employee_id, current_user.id, "Отклонен через панель управления сотрудниками")
        
        if success:
            await callback.answer(
                get_text('employee_management.employee_rejected', language=lang),
                show_alert=True
            )
            
            # Возвращаемся к списку
            await show_employee_list(callback, db, roles, active_role, user)
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка отклонения сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ БЛОКИРОВКА/РАЗБЛОКИРОВКА СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("block_employee_"))
async def block_employee(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Заблокировать сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])
        
        # Получаем ID пользователя из базы данных по telegram_id
        current_user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not current_user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        auth_service = AuthService(db)
        success = auth_service.block_user(employee_id, current_user.id, "Заблокирован через панель управления сотрудниками")
        
        if success:
            await callback.answer(
                get_text('employee_management.employee_blocked', language=lang),
                show_alert=True
            )
            
            # Возвращаемся к списку
            await show_employee_list(callback, db, roles, active_role, user)
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка блокировки сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("unblock_employee_"))
async def unblock_employee(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Разблокировать сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])
        
        # Получаем ID пользователя из базы данных по telegram_id
        current_user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not current_user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        auth_service = AuthService(db)
        success = auth_service.approve_user(employee_id, current_user.id, "Разблокирован через панель управления сотрудниками")
        
        if success:
            await callback.answer(
                get_text('employee_management.employee_unblocked', language=lang),
                show_alert=True
            )
            
            # Возвращаемся к списку
            await show_employee_list(callback, db, roles, active_role, user)
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка разблокировки сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ РЕДАКТИРОВАНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("edit_employee_name_"))
async def edit_employee_name(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Редактировать ФИО сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
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
        user_mgmt_service = UserManagementService(db)
        employee = user_mgmt_service.get_user_by_id(employee_id)
        
        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'action': 'edit_name'
        })
        
        await state.set_state(EmployeeManagementStates.editing_full_name)
        
        # Запрашиваем новое ФИО
        await callback.message.edit_text(
            f"📝 Введите новое ФИО для {_format_employee_name(employee)}:\n\n"
            f"Текущее ФИО: {employee.first_name or ''} {employee.last_name or ''}",
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования ФИО сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("edit_employee_phone_"))
async def edit_employee_phone(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Редактировать телефон сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
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
        user_mgmt_service = UserManagementService(db)
        employee = user_mgmt_service.get_user_by_id(employee_id)
        
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
            f"📱 Введите новый номер телефона для {_format_employee_name(employee)}:\n\n"
            f"Текущий телефон: {employee.phone or 'Не указан'}",
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования телефона сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(EmployeeManagementStates.editing_full_name)
async def process_employee_name_edit(message: Message, state: FSMContext, db: Session):
    """Обработать изменение ФИО сотрудника"""
    try:
        new_name = message.text.strip()
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        
        if not new_name:
            await message.answer("ФИО не может быть пустым. Попробуйте еще раз.")
            return
        
        # Обновляем ФИО
        user = db.query(User).filter(User.id == target_employee_id).first()
        if user:
            # Разделяем ФИО на имя и фамилию
            name_parts = new_name.split()
            if len(name_parts) >= 2:
                user.first_name = name_parts[0]
                user.last_name = ' '.join(name_parts[1:])
            else:
                user.first_name = new_name
                user.last_name = None
            
            db.commit()
            
            await message.answer(f"✅ ФИО обновлено: {new_name}")
        else:
            await message.answer("❌ Сотрудник не найден")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки изменения ФИО: {e}")
        await message.answer("Произошла ошибка при обновлении ФИО")
        await state.clear()


@router.message(EmployeeManagementStates.editing_phone)
async def process_employee_phone_edit(message: Message, state: FSMContext, db: Session):
    """Обработать изменение телефона сотрудника"""
    try:
        new_phone = message.text.strip()
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        
        if not new_phone:
            await message.answer("Номер телефона не может быть пустым. Попробуйте еще раз.")
            return
        
        # Обновляем телефон
        user = db.query(User).filter(User.id == target_employee_id).first()
        if user:
            user.phone = new_phone
            db.commit()
            
            await message.answer(f"✅ Телефон обновлен: {new_phone}")
        else:
            await message.answer("❌ Сотрудник не найден")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки изменения телефона: {e}")
        await message.answer("Произошла ошибка при обновлении телефона")
        await state.clear()


@router.callback_query(F.data.startswith("change_employee_role_"))
async def change_employee_role(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Изменить роль сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
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
        user_mgmt_service = UserManagementService(db)
        employee = user_mgmt_service.get_user_by_id(employee_id)
        
        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Получаем текущие роли
        user_roles = []
        if employee.roles:
            try:
                user_roles = json.loads(employee.roles)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга ролей пользователя {employee.id}: {e}")
                user_roles = []
        
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
        message_text += f"Текущие роли: {', '.join(user_roles) if user_roles else 'Нет ролей'}"
        
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


# ═══ УДАЛЕНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("delete_employee_"))
async def delete_employee(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Удалить сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])
        
        # Получаем ID пользователя из базы данных по telegram_id
        current_user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not current_user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        auth_service = AuthService(db)
        success = auth_service.delete_user(employee_id, current_user.id, "Удален через панель управления сотрудниками")
        
        if success:
            await callback.answer(
                get_text('employee_management.employee_deleted', language=lang),
                show_alert=True
            )
            
            # Возвращаемся к списку
            await show_employee_list(callback, db, roles, active_role, user)
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка удаления сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ СПЕЦИАЛИЗАЦИИ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("change_employee_specialization_"))
async def change_employee_specialization(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Изменить специализацию сотрудника"""
    lang = callback.from_user.language_code or 'ru'
    
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
        user_mgmt_service = UserManagementService(db)
        employee = user_mgmt_service.get_user_by_id(employee_id)
        
        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Получаем текущие специализации
        user_specializations = []
        if employee.specialization:
            try:
                user_specializations = json.loads(employee.specialization)
            except:
                # Если не JSON, пробуем как строку с запятыми
                if isinstance(employee.specialization, str):
                    user_specializations = [s.strip() for s in employee.specialization.split(',') if s.strip()]
                else:
                    user_specializations = []
        
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
            message_text += "Нет специализаций"
        
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


# ═══ ПОИСК СОТРУДНИКОВ ═══

@router.callback_query(F.data == "employee_mgmt_search")
async def start_employee_search(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Начать поиск сотрудников"""
    lang = callback.from_user.language_code or 'ru'
    
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
        
        # Устанавливаем состояние поиска
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка начала поиска сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ СПЕЦИАЛИЗАЦИЯМИ ═══

@router.callback_query(F.data == "employee_mgmt_specializations")
async def show_employee_specializations_management(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать управление специализациями сотрудников"""
    lang = callback.from_user.language_code or 'ru'
    
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
        spec_service = SpecializationService(db)
        detailed_stats = spec_service.get_detailed_specialization_stats()
        
        # Формируем сообщение со статистикой и списком сотрудников
        message_text = "🛠️ Статистика специализаций сотрудников:\n\n"
        
        if detailed_stats:
            for spec_key, spec_data in detailed_stats.items():
                # Переводим название специализации
                spec_name = get_text(f'specializations.{spec_key}', language=lang)
                count = spec_data['count']
                employees = spec_data['employees']
                
                message_text += f"• {spec_name}: {count} сотрудников\n"
                
                # Добавляем список сотрудников
                if employees:
                    for employee in employees:
                        # Формируем имя сотрудника
                        if employee.first_name and employee.last_name:
                            employee_name = f"{employee.first_name} {employee.last_name}"
                        elif employee.first_name:
                            employee_name = employee.first_name
                        elif employee.username:
                            employee_name = f"@{employee.username}"
                        else:
                            employee_name = f"ID: {employee.telegram_id}"
                        
                        message_text += f"  - {employee_name}\n"
                else:
                    message_text += f"  - Нет сотрудников\n"
                
                message_text += "\n"
        else:
            message_text += "Нет данных о специализациях\n"
        
        message_text += "Для управления специализациями конкретного сотрудника используйте 'Управление пользователями' → выберите сотрудника → 'Специализации'"
        
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
async def toggle_role(callback: CallbackQuery, state: FSMContext):
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
        lang = callback.from_user.language_code or 'ru'
        
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения роли: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "role_save", EmployeeManagementStates.selecting_roles)
async def save_employee_roles(callback: CallbackQuery, state: FSMContext, db: Session):
    """Сохранить роли сотрудника"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        
        # Проверяем, изменились ли роли
        if set(original_roles) == set(current_roles):
            await callback.answer("Роли не изменились", show_alert=True)
            await state.clear()
            return
        
        # Запрашиваем комментарий
        await state.update_data({'action': 'roles_change'})
        await state.set_state(EmployeeManagementStates.waiting_for_role_comment)
        
        lang = callback.from_user.language_code or 'ru'
        await callback.message.edit_text(
            get_text('moderation.enter_role_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения ролей: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "role_cancel", EmployeeManagementStates.selecting_roles)
async def cancel_roles_editing(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отменить редактирование ролей"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        
        await state.clear()
        
        # Возвращаемся к информации о сотруднике
        await _return_to_employee_info(callback, db, target_employee_id)
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования ролей: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(EmployeeManagementStates.waiting_for_role_comment)
async def process_role_change_comment(message: Message, state: FSMContext, db: Session):
    """Обработать комментарий для изменения ролей"""
    try:
        comment = message.text
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        current_roles = data.get('current_roles', [])
        
        logger.debug(f" Обработка комментария ролей. target_employee_id={target_employee_id}, current_roles={current_roles}")
        
        # Получаем ID пользователя, который вносит изменения
        current_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not current_user:
            logger.error(f"User not found: telegram_id={message.from_user.id}")
            await message.answer("❌ Ошибка: пользователь не найден")
            await state.clear()
            return
        
        # Обновляем роли пользователя
        user = db.query(User).filter(User.id == target_employee_id).first()
        if user:
            logger.debug(f" Найден пользователь для обновления ролей: {user.id}")
            
            old_roles = []
            if user.roles:
                try:
                    old_roles = json.loads(user.roles)
                except:
                    old_roles = []
            
            logger.debug(f" Старые роли: {old_roles}, новые роли: {current_roles}")
            
            user.roles = json.dumps(current_roles)
            if current_roles:
                user.role = current_roles[0]  # Первая роль как основная
            
            # Создаем запись в аудит логе
            try:
                from uk_management_bot.database.models.audit import AuditLog
                audit = AuditLog(
                    action="role_change",
                    user_id=current_user.id,  # ID пользователя, который вносит изменения
                    telegram_user_id=user.telegram_id,  # Telegram ID пользователя, у которого изменяются роли
                    details=json.dumps({
                        "target_user_id": target_employee_id,
                        "old_roles": old_roles,
                        "new_roles": current_roles,
                        "comment": comment,
                        "timestamp": datetime.now().isoformat()
                    })
                )
                db.add(audit)
                logger.debug(f" AuditLog создан успешно")
            except Exception as audit_error:
                logger.error(f"Failed to create AuditLog: {audit_error}")
                # Продолжаем выполнение даже если аудит не удался
            
            db.commit()
            logger.debug(f" Роли успешно обновлены и сохранены")
        else:
            logger.error(f"Employee not found: ID {target_employee_id}")
            await message.answer("❌ Ошибка: сотрудник не найден")
            await state.clear()
            return
        
        await state.clear()
        
        lang = message.from_user.language_code or 'ru'
        await message.answer(
            f"✅ Роли сотрудника обновлены: {', '.join(current_roles) if current_roles else 'Нет ролей'}"
        )
        
    except Exception as e:
        logger.error(f"Error processing role change comment: {e}")
        await message.answer("❌ Произошла ошибка при обновлении ролей")
        await state.clear()


@router.callback_query(F.data.startswith("spec_toggle_"), EmployeeManagementStates.selecting_specializations)
async def toggle_specialization(callback: CallbackQuery, state: FSMContext):
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
        lang = callback.from_user.language_code or 'ru'
        
        await callback.message.edit_reply_markup(
            reply_markup=get_specializations_selection_keyboard(current_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "spec_save", EmployeeManagementStates.selecting_specializations)
async def save_employee_specializations(callback: CallbackQuery, state: FSMContext, db: Session):
    """Сохранить специализации сотрудника"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        original_specializations = data.get('original_specializations', [])
        current_specializations = data.get('current_specializations', [])
        
        # Проверяем, изменились ли специализации
        if set(original_specializations) == set(current_specializations):
            await callback.answer("Специализации не изменились", show_alert=True)
            await state.clear()
            return
        
        # Запрашиваем комментарий
        await state.update_data({'action': 'specializations_change'})
        await state.set_state(EmployeeManagementStates.waiting_for_specialization_comment)
        
        lang = callback.from_user.language_code or 'ru'
        await callback.message.edit_text(
            get_text('moderation.enter_specialization_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "spec_cancel", EmployeeManagementStates.selecting_specializations)
async def cancel_specializations_editing(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отменить редактирование специализаций"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        
        await state.clear()
        
        # Возвращаемся к информации о сотруднике
        await _return_to_employee_info(callback, db, target_employee_id)
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования специализаций: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(EmployeeManagementStates.waiting_for_specialization_comment)
async def process_specialization_change_comment(message: Message, state: FSMContext, db: Session):
    """Обработать комментарий для изменения специализаций"""
    try:
        comment = message.text
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        current_specializations = data.get('current_specializations', [])
        
        # Получаем ID пользователя, который вносит изменения
        current_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not current_user:
            await message.answer("❌ Ошибка: пользователь не найден")
            await state.clear()
            return
        
        # Сохраняем специализации напрямую в базу (обходя проверки сервиса)
        user = db.query(User).filter(User.id == target_employee_id).first()
        if user:
            old_specializations = []
            if user.specialization:
                try:
                    old_specializations = json.loads(user.specialization)
                except:
                    if isinstance(user.specialization, str):
                        old_specializations = [s.strip() for s in user.specialization.split(',') if s.strip()]
            
            # Сохраняем специализации как JSON строку
            user.specialization = json.dumps(current_specializations)
            
            # Создаем запись в аудит логе
            try:
                from uk_management_bot.database.models.audit import AuditLog
                audit = AuditLog(
                    action="specialization_change",
                    user_id=current_user.id,  # ID пользователя, который вносит изменения
                    telegram_user_id=user.telegram_id,  # Telegram ID пользователя, у которого изменяются специализации
                    details=json.dumps({
                        "target_user_id": target_employee_id,
                        "old_specializations": old_specializations,
                        "new_specializations": current_specializations,
                        "comment": comment,
                        "timestamp": datetime.now().isoformat()
                    })
                )
                db.add(audit)
            except Exception as audit_error:
                logger.error(f"Ошибка создания AuditLog: {audit_error}")
                # Продолжаем выполнение даже если аудит не удался
            
            db.commit()
            success = True
        else:
            success = False
        
        await state.clear()
        
        if success:
            lang = message.from_user.language_code or 'ru'
            await message.answer(
                f"✅ Специализации сотрудника обновлены: {', '.join(current_specializations) if current_specializations else 'Нет специализаций'}"
            )
        else:
            await message.answer("❌ Ошибка при сохранении специализаций")
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария специализаций: {e}")
        await message.answer("❌ Произошла ошибка при обновлении специализаций")
        await state.clear()


# ═══ НАВИГАЦИЯ ═══

@router.callback_query(F.data == "no_action")
async def no_action_handler(callback: CallbackQuery):
    """Обработчик для кнопок без действия"""
    await callback.answer()


@router.callback_query(F.data == "admin_panel")
async def back_to_admin_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Вернуться к админ панели"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        from uk_management_bot.keyboards.admin import get_manager_main_keyboard
        
        await callback.message.edit_text(
            get_text('admin.panel_title', language=lang),
            reply_markup=get_manager_main_keyboard()
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к админ панели: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
