"""
Обработчики для управления пользователями

Содержит обработчики для:
- Панели управления пользователями
- Списков и поиска пользователей
- Действий модерации
- Управления ролями и специализациями
"""

import logging
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from services.user_management_service import UserManagementService
from services.specialization_service import SpecializationService
from services.auth_service import AuthService
from keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_list_keyboard,
    get_user_actions_keyboard,
    get_roles_management_keyboard,
    get_specializations_selection_keyboard,
    get_cancel_keyboard,
    get_confirmation_keyboard
)
from states.user_management import UserManagementStates
from utils.helpers import get_text
from database.models.user import User

logger = logging.getLogger(__name__)
router = Router()


# ═══ ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ═══

@router.callback_query(F.data == "user_management_panel")
async def show_user_management_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None):
    """Показать панель управления пользователями"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Получаем статистику пользователей
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        # Показываем главное меню
        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения панели управления пользователями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "user_mgmt_main")
async def back_to_main_panel(callback: CallbackQuery, db: Session, roles: list = None):
    """Вернуться к главному меню панели управления"""
    await show_user_management_panel(callback, db, roles)


@router.callback_query(F.data == "user_mgmt_stats")
async def show_user_stats(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать статистику пользователей"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        stats_text = user_mgmt_service.format_stats_message(stats, lang)
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения статистики: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ СПИСКИ ПОЛЬЗОВАТЕЛЕЙ ═══

@router.callback_query(F.data.startswith("user_mgmt_list_"))
async def show_user_list(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать список пользователей"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Парсим callback data: user_mgmt_list_{type}_{page}
        parts = callback.data.split('_')
        list_type = parts[3]  # pending, approved, blocked, staff
        page = int(parts[4]) if len(parts) > 4 else 1
        
        user_mgmt_service = UserManagementService(db)
        
        # Получаем данные в зависимости от типа списка
        if list_type == 'staff':
            users_data = user_mgmt_service.get_staff_users(page=page)
        else:
            users_data = user_mgmt_service.get_users_by_status(list_type, page=page)
        
        # Формируем заголовок
        title_key = f"user_management.{list_type}_users"
        if list_type == 'staff':
            title_key = "user_management.staff_users"
        
        title = get_text(title_key, language=lang)
        total = users_data.get('total', 0)
        
        message_text = f"{title}\n\n"
        if total > 0:
            message_text += get_text('pagination.info', language=lang).format(
                page=page,
                total_pages=users_data.get('total_pages', 1),
                total_items=total
            )
        else:
            message_text += get_text('user_management.no_users_found', language=lang)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_user_list_keyboard(users_data, list_type, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения списка пользователей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ДЕЙСТВИЯ С ПОЛЬЗОВАТЕЛЯМИ ═══

@router.callback_query(F.data.startswith("user_mgmt_user_"))
async def show_user_details(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать детали пользователя и доступные действия"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Парсим user_id из callback data
        user_id = int(callback.data.split('_')[-1])
        
        user_mgmt_service = UserManagementService(db)
        user = user_mgmt_service.get_user_by_id(user_id)
        
        if not user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Форматируем информацию о пользователе
        user_info = user_mgmt_service.format_user_info(user, lang, detailed=True)
        
        await callback.message.edit_text(
            user_info,
            reply_markup=get_user_actions_keyboard(user, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения деталей пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ДЕЙСТВИЯ МОДЕРАЦИИ ═══

@router.callback_query(F.data.startswith("user_action_approve_"))
async def handle_approve_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                             user: User, roles: list = None):
    """Обработать одобрение пользователя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Получаем ID целевого пользователя
        target_user_id = int(callback.data.split('_')[-1])
        
        # Сохраняем данные в состоянии FSM
        await state.update_data({
            'action': 'approve',
            'target_user_id': target_user_id,
            'manager_id': user.id
        })
        
        await state.set_state(UserManagementStates.waiting_for_approval_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_approval_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки одобрения пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("user_action_block_"))
async def handle_block_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                           user: User, roles: list = None):
    """Обработать блокировку пользователя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        await state.update_data({
            'action': 'block',
            'target_user_id': target_user_id,
            'manager_id': user.id
        })
        
        await state.set_state(UserManagementStates.waiting_for_block_reason)
        
        await callback.message.edit_text(
            get_text('moderation.enter_block_reason', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки блокировки пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("user_action_unblock_"))
async def handle_unblock_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                             user: User, roles: list = None):
    """Обработать разблокировку пользователя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        await state.update_data({
            'action': 'unblock',
            'target_user_id': target_user_id,
            'manager_id': user.id
        })
        
        await state.set_state(UserManagementStates.waiting_for_unblock_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_unblock_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки разблокировки пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОБРАБОТКА КОММЕНТАРИЕВ ═══

@router.message(UserManagementStates.waiting_for_approval_comment)
async def process_approval_comment(message: Message, state: FSMContext, db: Session):
    """Обработать комментарий для одобрения"""
    lang = message.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        comment = message.text
        
        # Выполняем одобрение
        auth_service = AuthService(db)
        success = auth_service.approve_user(target_user_id, manager_id, comment)
        
        if success:
            # Получаем обновленную информацию о пользователе
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.user_approved_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария одобрения: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_block_reason)
async def process_block_reason(message: Message, state: FSMContext, db: Session):
    """Обработать причину блокировки"""
    lang = message.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        reason = message.text
        
        # Выполняем блокировку
        auth_service = AuthService(db)
        success = auth_service.block_user(target_user_id, manager_id, reason)
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.user_blocked_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем обновленные детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины блокировки: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_unblock_comment)
async def process_unblock_comment(message: Message, state: FSMContext, db: Session):
    """Обработать комментарий для разблокировки"""
    lang = message.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        comment = message.text
        
        # Выполняем разблокировку
        auth_service = AuthService(db)
        success = auth_service.unblock_user(target_user_id, manager_id, comment)
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.user_unblocked_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем обновленные детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария разблокировки: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ ОТМЕНА ОПЕРАЦИЙ ═══

@router.callback_query(F.data == "user_mgmt_cancel")
async def cancel_user_management_operation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отменить текущую операцию управления пользователями"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        await state.clear()
        
        # Возвращаемся к главному меню панели управления
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены операции: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ЗАГЛУШКИ ДЛЯ НЕАКТИВНЫХ КНОПОК ═══

@router.callback_query(F.data == "user_mgmt_nop")
async def user_management_nop(callback: CallbackQuery):
    """Заглушка для неактивных кнопок"""
    await callback.answer()


# ═══ НАВИГАЦИЯ ═══

@router.callback_query(F.data == "user_mgmt_back_to_list")
async def back_to_user_list(callback: CallbackQuery, state: FSMContext, db: Session):
    """Вернуться к списку пользователей"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        # Очищаем состояние
        await state.clear()
        
        # Возвращаемся к главному меню панели управления
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ РОЛЯМИ ═══

@router.callback_query(F.data.startswith("user_roles_"))
async def show_user_roles_management(callback: CallbackQuery, state: FSMContext, db: Session, 
                                   user: User, roles: list = None):
    """Показать управление ролями пользователя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        auth_service = AuthService(db)
        user_roles = auth_service.get_user_roles(target_user_id)
        
        # Сохраняем данные в состоянии
        await state.update_data({
            'target_user_id': target_user_id,
            'manager_id': user.id,
            'original_roles': user_roles.copy(),
            'current_roles': user_roles.copy()
        })
        
        await state.set_state(UserManagementStates.selecting_roles)
        
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
        
        message_text = get_text('moderation.select_roles', language=lang).format(user_name=user_name)
        message_text += f"\n\n{get_text('moderation.current_roles', language=lang)}: "
        message_text += user_mgmt_service._format_user_roles(target_user, lang)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_roles_management_keyboard(user_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения управления ролями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("role_add_"), UserManagementStates.selecting_roles)
async def add_role_to_user(callback: CallbackQuery, state: FSMContext):
    """Добавить роль пользователю"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        role = callback.data.split('_')[-1]
        data = await state.get_data()
        current_roles = data.get('current_roles', [])
        
        if role not in current_roles:
            current_roles.append(role)
            await state.update_data(current_roles=current_roles)
        
        # Обновляем клавиатуру
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка добавления роли: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("role_remove_"), UserManagementStates.selecting_roles)
async def remove_role_from_user(callback: CallbackQuery, state: FSMContext):
    """Удалить роль у пользователя"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        role = callback.data.split('_')[-1]
        data = await state.get_data()
        current_roles = data.get('current_roles', [])
        
        # Проверяем, что не удаляем последнюю роль
        if len(current_roles) <= 1:
            await callback.answer(
                get_text('moderation.cannot_remove_last_role', language=lang),
                show_alert=True
            )
            return
        
        if role in current_roles:
            current_roles.remove(role)
            await state.update_data(current_roles=current_roles)
        
        # Обновляем клавиатуру
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка удаления роли: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "roles_save", UserManagementStates.selecting_roles)
async def save_user_roles(callback: CallbackQuery, state: FSMContext):
    """Сохранить изменения ролей"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        
        # Проверяем, есть ли изменения
        if set(original_roles) == set(current_roles):
            await callback.answer(
                get_text('moderation.no_changes_made', language=lang)
            )
            await state.clear()
            return
        
        # Переходим к вводу комментария
        await state.update_data({'action': 'roles_change'})
        await state.set_state(UserManagementStates.waiting_for_role_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_role_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения ролей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "roles_cancel", UserManagementStates.selecting_roles)
async def cancel_roles_editing(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отменить редактирование ролей"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        
        await state.clear()
        
        # Возвращаемся к деталям пользователя
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        
        if target_user:
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await callback.message.edit_text(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        
        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования ролей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserManagementStates.waiting_for_role_comment)
async def process_role_change_comment(message: Message, state: FSMContext, db: Session):
    """Обработать комментарий к изменению ролей"""
    lang = message.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        comment = message.text
        
        auth_service = AuthService(db)
        
        # Определяем добавленные и удаленные роли
        added_roles = set(current_roles) - set(original_roles)
        removed_roles = set(original_roles) - set(current_roles)
        
        success = True
        
        # Добавляем новые роли
        for role in added_roles:
            if not auth_service.assign_role(target_user_id, role, manager_id, comment):
                success = False
        
        # Удаляем роли
        for role in removed_roles:
            if not auth_service.remove_role(target_user_id, role, manager_id, comment):
                success = False
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.roles_updated_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем обновленные детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария к изменению ролей: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ УПРАВЛЕНИЕ СПЕЦИАЛИЗАЦИЯМИ ═══

@router.callback_query(F.data.startswith("user_specializations_"))
async def show_user_specializations_management(callback: CallbackQuery, state: FSMContext, db: Session, 
                                             user: User, roles: list = None):
    """Показать управление специализациями пользователя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        spec_service = SpecializationService(db)
        user_specializations = spec_service.get_user_specializations(target_user_id)
        
        # Сохраняем данные в состоянии
        await state.update_data({
            'target_user_id': target_user_id,
            'manager_id': user.id,
            'original_specializations': user_specializations.copy(),
            'current_specializations': user_specializations.copy()
        })
        
        await state.set_state(UserManagementStates.selecting_specializations)
        
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
        
        message_text = get_text('specializations.select_specializations', language=lang).format(user_name=user_name)
        message_text += f"\n\n{get_text('specializations.current_specializations', language=lang)}: "
        message_text += spec_service.format_specializations_list(user_specializations, lang)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_specializations_selection_keyboard(user_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения управления специализациями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("spec_toggle_"), UserManagementStates.selecting_specializations)
async def toggle_specialization(callback: CallbackQuery, state: FSMContext):
    """Переключить специализацию (добавить/удалить)"""
    lang = callback.from_user.language_code or 'ru'
    
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
        await callback.message.edit_reply_markup(
            reply_markup=get_specializations_selection_keyboard(current_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "spec_save", UserManagementStates.selecting_specializations)
async def save_user_specializations(callback: CallbackQuery, state: FSMContext):
    """Сохранить изменения специализаций"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        original_specializations = data.get('original_specializations', [])
        current_specializations = data.get('current_specializations', [])
        
        # Проверяем, есть ли изменения
        if set(original_specializations) == set(current_specializations):
            await callback.answer(
                get_text('moderation.no_changes_made', language=lang)
            )
            await state.clear()
            return
        
        # Переходим к вводу комментария
        await state.update_data({'action': 'specializations_change'})
        await state.set_state(UserManagementStates.waiting_for_specialization_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_specialization_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "spec_cancel", UserManagementStates.selecting_specializations)
async def cancel_specializations_editing(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отменить редактирование специализаций"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        
        await state.clear()
        
        # Возвращаемся к деталям пользователя
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        
        if target_user:
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await callback.message.edit_text(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        
        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования специализаций: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserManagementStates.waiting_for_specialization_comment)
async def process_specialization_change_comment(message: Message, state: FSMContext, db: Session):
    """Обработать комментарий к изменению специализаций"""
    lang = message.from_user.language_code or 'ru'
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        current_specializations = data.get('current_specializations', [])
        comment = message.text
        
        spec_service = SpecializationService(db)
        success = spec_service.set_user_specializations(
            target_user_id, 
            current_specializations, 
            manager_id, 
            comment
        )
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('specializations.specializations_updated', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем обновленные детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария к изменению специализаций: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ ИНТЕГРАЦИЯ С АДМИН ПАНЕЛЬЮ ═══

@router.callback_query(F.data == "admin_panel")
async def back_to_admin_panel(callback: CallbackQuery):
    """Вернуться в админ панель"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        from keyboards.admin import get_manager_main_keyboard
        
        await callback.message.answer(
            "Панель менеджера",
            reply_markup=get_manager_main_keyboard()
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата в админ панель: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
