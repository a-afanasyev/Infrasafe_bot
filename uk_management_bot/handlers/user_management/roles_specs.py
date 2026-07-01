"""Управление ролями и специализациями пользователя."""
import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.keyboards.user_management import (
    get_user_actions_keyboard,
    get_roles_management_keyboard,
    get_specializations_selection_keyboard,
    get_cancel_keyboard,
)
from uk_management_bot.states.user_management import UserManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router

logger = logging.getLogger(__name__)


# ═══ УПРАВЛЕНИЕ РОЛЯМИ ═══

@router.callback_query(F.data.startswith("user_roles_"))
async def show_user_roles_management(callback: CallbackQuery, state: FSMContext, db: Session, 
                                   roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать управление ролями пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        auth_service = AuthService(db)
        user_roles = auth_service.get_user_roles(target_user_id)
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        # Сохраняем данные в состоянии
        await state.update_data({
            'target_user_id': target_user_id,
            'manager_id': manager.id,  # Используем внутренний ID из базы данных
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
async def add_role_to_user(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Добавить роль пользователю"""
    lang = language
    
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
async def remove_role_from_user(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Удалить роль у пользователя"""
    lang = language
    
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
async def save_user_roles(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить изменения ролей"""
    lang = language

    try:
        data = await state.get_data()
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
async def cancel_roles_editing(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отменить редактирование ролей"""
    lang = language
    
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
async def process_role_change_comment(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать комментарий к изменению ролей"""
    lang = language
    
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
                                             roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать управление специализациями пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        spec_service = SpecializationService(db)
        user_specializations = spec_service.get_user_specializations(target_user_id)
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        # Сохраняем данные в состоянии
        await state.update_data({
            'target_user_id': target_user_id,
            'manager_id': manager.id,  # Используем внутренний ID из базы данных
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
async def toggle_specialization(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Переключить специализацию (добавить/удалить)"""
    lang = language
    
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
async def save_user_specializations(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить изменения специализаций"""
    lang = language
    
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
async def cancel_specializations_editing(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отменить редактирование специализаций"""
    lang = language
    
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
async def process_specialization_change_comment(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать комментарий к изменению специализаций"""
    lang = language
    
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


