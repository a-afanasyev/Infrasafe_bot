"""Клавиатуры с верификацией, список/поиск/детали пользователей."""
import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.keyboards.user_management import (
    get_user_list_keyboard,
    get_user_actions_keyboard,
    get_cancel_keyboard,
)
from uk_management_bot.states.user_management import UserManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router

logger = logging.getLogger(__name__)


# ═══ СПИСКИ ПОЛЬЗОВАТЕЛЕЙ ═══

@router.callback_query(F.data.startswith("user_mgmt_list_"))
async def show_user_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать список пользователей"""
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
        
        try:
            await callback.message.edit_text(
                message_text,
                reply_markup=get_user_list_keyboard(users_data, list_type, lang)
            )
        except Exception as edit_error:
            # Если сообщение не изменилось, просто отвечаем на callback
            if "message is not modified" in str(edit_error):
                await callback.answer(get_text('user_mgmt.handlers.data_up_to_date', language=lang))
            else:
                raise edit_error
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения списка пользователей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ПОИСК ЖИТЕЛЕЙ (MGR-02) ═══

@router.callback_query(F.data == "user_mgmt_search")
async def start_resident_search(callback: CallbackQuery, state: FSMContext, db: Session = None, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """MGR-02: вход в поиск жителей. Раньше клик «🔍 Поиск» был no-op (не было
    prompt + FSM-state). Аналог employee-поиска, но фильтр — только applicant."""
    lang = language

    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return

    try:
        await callback.message.edit_text(
            get_text('user_management.search_instructions', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        await state.set_state(UserManagementStates.waiting_for_search_query)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка начала поиска жителей: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.message(UserManagementStates.waiting_for_search_query)
async def handle_resident_search_query(message: Message, state: FSMContext, db: Session = None, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """MGR-02: обработка введённого запроса поиска жителей.

    Ищем только жителей (applicant) по имени/фамилии/username/телефону через
    UserManagementService.search_residents → кнопки ведут в карточку
    `user_mgmt_user_<id>` (show_user_details).
    """
    lang = language

    if not has_admin_access(roles=roles, user=user):
        await message.answer(get_text('errors.permission_denied', language=lang))
        await state.clear()
        return

    raw_query = (message.text or "").strip()
    if not raw_query:
        await message.answer(get_text('user_management.search_empty_query', language=lang))
        return

    try:
        residents = UserManagementService(db).search_residents(raw_query, limit=20)

        if not residents:
            await message.answer(
                get_text('user_management.search_not_found', language=lang),
                reply_markup=get_cancel_keyboard(lang)
            )
            await state.clear()
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = []
        for resident in residents:
            name = f"{resident.first_name or ''} {resident.last_name or ''}".strip()
            if not name:
                name = f"@{resident.username}" if resident.username else f"ID: {resident.telegram_id}"
            rows.append([InlineKeyboardButton(text=name, callback_data=f"user_mgmt_user_{resident.id}")])

        await message.answer(
            get_text('user_management.search_results_header', language=lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка поиска жителей: {e}")
        await message.answer(get_text('errors.unknown_error', language=lang))
        await state.clear()


# ═══ ДЕЙСТВИЯ С ПОЛЬЗОВАТЕЛЯМИ ═══

@router.callback_query(F.data.startswith("user_mgmt_user_"))
async def show_user_details(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать детали пользователя и доступные действия"""
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


