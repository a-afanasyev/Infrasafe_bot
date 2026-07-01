"""Менеджер: создание приглашений (FSM)."""
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_invite_role_keyboard,
    get_invite_specialization_keyboard,
    get_invite_expiry_keyboard,
    get_invite_confirmation_keyboard,
)
from uk_management_bot.keyboards.base import get_user_contextual_keyboard
from uk_management_bot.services.invite_service import InviteService

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.states.invite_creation import InviteCreationStates

from ._router import router

from .shared import ADMIN_CREATE_INVITE_TEXTS

logger = logging.getLogger(__name__)


# ===== ОБРАБОТЧИКИ СОЗДАНИЯ ПРИГЛАШЕНИЙ =====

@router.message(F.text.in_(ADMIN_CREATE_INVITE_TEXTS))
async def start_invite_creation(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Начать процесс создания приглашения"""
    lang = language
    
    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("invites.manager_only", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer(
        get_text("invites.select_role", language=lang),
        reply_markup=get_invite_role_keyboard()
    )


@router.callback_query(F.data.startswith("invite_role_"))
async def handle_invite_role_selection(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик выбора роли для приглашения"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

    # Извлекаем роль из callback_data
    role = callback.data.replace("invite_role_", "")
    
    if role not in ["applicant", "executor", "manager", "inspector"]:
        await callback.answer(get_text("admin.handlers.invalid_role", language=lang))
        return
    
    # Сохраняем роль в состоянии
    await state.update_data(role=role)
    
    # Если выбрана роль executor, нужно выбрать специализацию
    if role == "executor":
        await callback.message.edit_text(
            get_text("invites.select_specialization", language=lang),
            reply_markup=get_invite_specialization_keyboard()
        )
        await state.set_state(InviteCreationStates.waiting_for_specialization)
    else:
        # Для других ролей переходим к выбору срока действия
        await callback.message.edit_text(
            get_text("invites.select_expiry", language=lang),
            reply_markup=get_invite_expiry_keyboard()
        )
        await state.set_state(InviteCreationStates.waiting_for_expiry)
    
    await callback.answer()


@router.callback_query(F.data.startswith("invite_spec_"), InviteCreationStates.waiting_for_specialization)
async def handle_invite_specialization_selection(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик выбора специализации для исполнителя"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

    # Извлекаем специализацию из callback_data
    specialization = callback.data.replace("invite_spec_", "")
    
    # Сохраняем специализацию в состоянии
    await state.update_data(specialization=specialization)
    
    # Переходим к выбору срока действия
    await callback.message.edit_text(
        get_text("invites.select_expiry", language=lang),
        reply_markup=get_invite_expiry_keyboard()
    )
    await state.set_state(InviteCreationStates.waiting_for_expiry)
    
    await callback.answer()


@router.callback_query(F.data.startswith("invite_expiry_"), InviteCreationStates.waiting_for_expiry)
async def handle_invite_expiry_selection(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик выбора срока действия приглашения"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

    # Извлекаем срок действия из callback_data
    expiry = callback.data.replace("invite_expiry_", "")
    
    # Преобразуем в часы
    expiry_hours = {
        "1h": 1,
        "24h": 24,
        "7d": 168  # 7 дней * 24 часа
    }.get(expiry, 24)
    
    # Сохраняем срок действия в состоянии
    await state.update_data(expiry_hours=expiry_hours)
    
    # Получаем данные из состояния для подтверждения
    data = await state.get_data()
    role = data.get("role", "unknown")
    specialization = data.get("specialization", "")
    expiry_text = {
        1: get_text("admin.handlers.expiry_1h", language=lang),
        24: get_text("admin.handlers.expiry_24h", language=lang),
        168: get_text("admin.handlers.expiry_7d", language=lang)
    }.get(expiry_hours, get_text("admin.handlers.expiry_24h", language=lang))
    
    # Формируем текст подтверждения
    role_name = get_text(f"roles.{role}", language=lang)
    confirmation_text = get_text("admin.handlers.invite_confirm_header", language=lang) + "\n\n"
    confirmation_text += get_text("admin.handlers.invite_confirm_role", language=lang).format(role_name=role_name) + "\n"

    if role == "executor" and specialization:
        spec_name = get_text(f"specializations.{specialization}", language=lang)
        confirmation_text += get_text("admin.handlers.invite_confirm_spec", language=lang).format(spec_name=spec_name) + "\n"

    confirmation_text += get_text("admin.handlers.invite_confirm_expiry", language=lang).format(expiry_text=expiry_text) + "\n\n"
    confirmation_text += get_text("admin.handlers.invite_confirm_instruction", language=lang)
    
    await callback.message.edit_text(
        confirmation_text,
        reply_markup=get_invite_confirmation_keyboard()
    )
    await state.set_state(InviteCreationStates.waiting_for_confirmation)
    
    await callback.answer()


@router.callback_query(F.data == "invite_confirm", InviteCreationStates.waiting_for_confirmation)
async def handle_invite_confirmation(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик подтверждения создания приглашения"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        role = data.get("role")
        specialization = data.get("specialization", "")
        expiry_hours = data.get("expiry_hours", 24)
        
        if not role:
            await callback.answer(get_text("admin.handlers.error_role_not_selected", language=lang))
            return
        
        # FS-09: генерируем приглашение РОВНО один раз. Раньше вызывались и
        # generate_invite_link, и generate_invite — каждый создаёт токен и пишет
        # audit-лог → дублирование (2 записи, 2 токена, причём показывался токен,
        # которого нет в ссылке). Ссылка — статический bot-URL (токен в неё не
        # входит), поэтому строим её инлайном из одного сгенерированного токена.
        from uk_management_bot.config.settings import settings
        invite_service = InviteService(db)
        token = invite_service.generate_invite(
            role=role,
            created_by=callback.from_user.id,
            specialization=specialization if role == "executor" else None,
            hours=expiry_hours
        )
        invite_link = f"https://t.me/{settings.BOT_USERNAME}"
        
        # Формируем текст с токеном
        role_name = get_text(f"roles.{role}", language=lang)
        expiry_text = {
            1: get_text("admin.handlers.expiry_1h", language=lang),
            24: get_text("admin.handlers.expiry_24h", language=lang),
            168: get_text("admin.handlers.expiry_7d", language=lang)
        }.get(expiry_hours, get_text("admin.handlers.expiry_24h", language=lang))

        success_text = get_text("admin.handlers.invite_created_header", language=lang) + "\n\n"
        success_text += get_text("admin.handlers.invite_confirm_role", language=lang).format(role_name=role_name) + "\n"

        if role == "executor" and specialization:
            spec_name = get_text(f"specializations.{specialization}", language=lang)
            success_text += get_text("admin.handlers.invite_confirm_spec", language=lang).format(spec_name=spec_name) + "\n"

        success_text += get_text("admin.handlers.invite_confirm_expiry", language=lang).format(expiry_text=expiry_text) + "\n\n"
        success_text += get_text("admin.handlers.invite_link_label", language=lang) + "\n\n"
        success_text += f"`{invite_link}`\n\n"
        success_text += get_text("admin.handlers.invite_instructions", language=lang).format(token=token)
        
        await callback.message.edit_text(
            success_text
        )
        await callback.message.answer(
            get_text("admin.handlers.back_to_admin_panel", language=lang),
            reply_markup=get_manager_main_keyboard(language=lang)
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Пользователь {callback.from_user.id} создал приглашение для роли {role}")
        
    except Exception as e:
        logger.error(f"Ошибка создания приглашения: {e}")
        await callback.message.edit_text(
            get_text("errors.unknown_error", language=lang)
        )
        await callback.message.answer(
            get_text("admin.handlers.back_to_admin_panel", language=lang),
            reply_markup=get_manager_main_keyboard(language=lang)
        )
        await state.clear()
    
    await callback.answer()


@router.callback_query(F.data == "invite_cancel")
async def handle_invite_cancel(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Обработчик отмены создания приглашения"""
    lang = language
    
    await callback.message.edit_text(
        get_text("buttons.operation_cancelled", language=lang)
    )
    await callback.message.answer(
        get_text("admin.handlers.back_to_admin_panel", language=lang),
        reply_markup=get_manager_main_keyboard(language=lang)
    )

    # Очищаем состояние
    await state.clear()
    
    await callback.answer()


