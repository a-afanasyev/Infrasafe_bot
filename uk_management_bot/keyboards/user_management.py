"""
Клавиатуры для управления пользователями

Содержит inline-клавиатуры для:
- Главного меню панели управления
- Списков пользователей с пагинацией
- Действий с пользователями
- Выбора ролей и специализаций
"""

from typing import Dict, List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.utils.helpers import get_text
# from uk_management_bot.database.models.user import User  # временно отключен


def get_user_management_main_keyboard(stats: Dict[str, int], language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Главное меню панели управления пользователями
    
    Args:
        stats: Статистика пользователей
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с главным меню
    """
    buttons = [
        # Статистика
        [InlineKeyboardButton(
            text=f"📊 {get_text('user_management.stats', language)}",
            callback_data="user_mgmt_stats"
        )],
        
        # Списки пользователей с счетчиками
        [InlineKeyboardButton(
            text=f"📝 {get_text('user_management.new_users', language)} ({stats.get('pending', 0)})",
            callback_data="user_mgmt_list_pending_1"
        )],
        [InlineKeyboardButton(
            text=f"✅ {get_text('user_management.approved_users', language)} ({stats.get('approved', 0)})",
            callback_data="user_mgmt_list_approved_1"
        )],
        [InlineKeyboardButton(
            text=f"🚫 {get_text('user_management.blocked_users', language)} ({stats.get('blocked', 0)})",
            callback_data="user_mgmt_list_blocked_1"
        )],
        [InlineKeyboardButton(
            text=f"👷 {get_text('user_management.staff_users', language)} ({stats.get('staff', 0)})",
            callback_data="user_mgmt_list_staff_1"
        )],
        
        # Поиск
        [InlineKeyboardButton(
            text=f"🔍 {get_text('user_management.search', language)}",
            callback_data="user_mgmt_search"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=get_text('buttons.back', language),
            callback_data="admin_panel"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_list_keyboard(users_data: Dict, list_type: str, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура списка пользователей с пагинацией
    
    Args:
        users_data: Данные пользователей с пагинацией
        list_type: Тип списка (pending, approved, blocked, staff)
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup со списком пользователей
    """
    buttons = []
    
    # Пользователи (по 5 на страницу для удобства)
    for user in users_data.get('users', []):
        user_name = _format_user_name(user)
        status_emoji = _get_status_emoji(user.status)
        
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} {user_name}",
            callback_data=f"user_mgmt_user_{user.id}"
        )])
    
    # Если пользователей нет
    if not users_data.get('users'):
        buttons.append([InlineKeyboardButton(
            text=get_text('user_management.no_users_found', language),
            callback_data="user_mgmt_nop"
        )])
    
    # Пагинация
    pagination_row = []
    if users_data.get('has_prev', False):
        pagination_row.append(InlineKeyboardButton(
            text="◀️",
            callback_data=f"user_mgmt_list_{list_type}_{users_data.get('page', 1) - 1}"
        ))
    
    # Показываем текущую страницу
    current_page = users_data.get('page', 1)
    total_pages = users_data.get('total_pages', 1)
    pagination_row.append(InlineKeyboardButton(
        text=f"{current_page}/{total_pages}",
        callback_data="user_mgmt_nop"
    ))
    
    if users_data.get('has_next', False):
        pagination_row.append(InlineKeyboardButton(
            text="▶️",
            callback_data=f"user_mgmt_list_{list_type}_{users_data.get('page', 1) + 1}"
        ))
    
    if pagination_row:
        buttons.append(pagination_row)
    
    # Обновить и назад
    buttons.append([
        InlineKeyboardButton(
            text=get_text('buttons.refresh', language),
            callback_data=f"user_mgmt_list_{list_type}_{current_page}"
        )
    ])
    
    buttons.append([InlineKeyboardButton(
        text=get_text('buttons.back', language),
        callback_data="user_mgmt_main"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_actions_keyboard(user, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура действий с пользователем
    
    Args:
        user: Объект пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с действиями
    """
    buttons = []
    
    # Действия зависят от текущего статуса
    if user.status == 'pending':
        buttons.append([InlineKeyboardButton(
            text=f"✅ {get_text('moderation.approve_user', language)}",
            callback_data=f"user_action_approve_{user.id}"
        )])
        buttons.append([InlineKeyboardButton(
            text=f"🚫 {get_text('moderation.block_user', language)}",
            callback_data=f"user_action_block_{user.id}"
        )])
    
    elif user.status == 'approved':
        buttons.append([InlineKeyboardButton(
            text=f"🚫 {get_text('moderation.block_user', language)}",
            callback_data=f"user_action_block_{user.id}"
        )])
    
    elif user.status == 'blocked':
        buttons.append([InlineKeyboardButton(
            text=f"🔓 {get_text('moderation.unblock_user', language)}",
            callback_data=f"user_action_unblock_{user.id}"
        )])
    
    # Управление ролями (всегда доступно)
    buttons.append([InlineKeyboardButton(
        text=f"👥 {get_text('moderation.manage_roles', language)}",
        callback_data=f"user_roles_{user.id}"
    )])
    
    # Специализации (только для исполнителей)
    if user.roles and 'executor' in user.roles:
        buttons.append([InlineKeyboardButton(
            text=f"🛠️ {get_text('moderation.manage_specializations', language)}",
            callback_data=f"user_specializations_{user.id}"
        )])

    # Управление дворами (для всех пользователей)
    buttons.append([InlineKeyboardButton(
        text=f"🏘️ {get_text('user_management.keyboards.manage_yards', language=language)}",
        callback_data=f"manage_user_yards_{user.telegram_id}"
    )])

    # Управление квартирами (для всех пользователей)
    buttons.append([InlineKeyboardButton(
        text=f"🏠 {get_text('user_management.keyboards.manage_apartments', language=language)}",
        callback_data=f"admin_manage_apartments_{user.telegram_id}"
    )])

    # Запрос дополнительных документов (всегда доступно)
    buttons.append([InlineKeyboardButton(
        text=f"📋 {get_text('moderation.request_documents', language)}",
        callback_data=f"user_action_request_docs_{user.id}"
    )])
    
    # Просмотр документов (если есть документы)
    from uk_management_bot.services.user_verification_service import UserVerificationService
    from sqlalchemy.orm import Session
    from uk_management_bot.database.session import session_scope

    try:
        # Получаем сессию базы данных (ARCH-013: контекст-менеджер гарантирует close)
        with session_scope() as db:
            verification_service = UserVerificationService(db)
            documents_summary = verification_service.get_user_documents_summary(user.id)

        if documents_summary['total_documents'] > 0:
            # Показываем количество документов
            buttons.append([InlineKeyboardButton(
                text=f"📄 {get_text('user_management.keyboards.documents', language=language)} ({documents_summary['total_documents']})",
                callback_data=f"user_action_view_documents_{user.id}"
            )])
        else:
            # Показываем кнопку без счетчика
            buttons.append([InlineKeyboardButton(
                text=f"📄 {get_text('user_management.keyboards.documents', language=language)}",
                callback_data=f"user_action_view_documents_{user.id}"
            )])
    except Exception as e:
        # В случае ошибки все равно показываем кнопку
        buttons.append([InlineKeyboardButton(
            text=f"📄 {get_text('user_management.keyboards.documents', language=language)}",
            callback_data=f"user_action_view_documents_{user.id}"
        )])
    
    # Удаление пользователя (всегда доступно, но с предупреждением)
    buttons.append([InlineKeyboardButton(
        text=f"🗑️ {get_text('moderation.delete_user', language)}",
        callback_data=f"user_action_delete_{user.id}"
    )])
    
    # Назад к списку
    buttons.append([InlineKeyboardButton(
        text=get_text('buttons.back', language),
        callback_data="user_mgmt_back_to_list"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_roles_management_keyboard(user_roles: List[str], language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура управления ролями пользователя
    
    Args:
        user_roles: Текущие роли пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup для управления ролями
    """
    buttons = []
    
    available_roles = ['applicant', 'executor', 'manager']
    
    # Группируем роли по 2 в ряд
    for i in range(0, len(available_roles), 2):
        row = []
        
        for j in range(2):
            if i + j < len(available_roles):
                role = available_roles[i + j]
                has_role = role in user_roles
                
                # Эмодзи для статуса
                checkbox = "☑️" if has_role else "☐"
                role_name = get_text(f"roles.{role}", language)
                
                action = "remove" if has_role else "add"
                
                row.append(InlineKeyboardButton(
                    text=f"{checkbox} {role_name}",
                    callback_data=f"role_{action}_{role}"
                ))
        
        buttons.append(row)
    
    # Кнопки управления
    buttons.append([
        InlineKeyboardButton(
            text=get_text('buttons.save', language),
            callback_data="roles_save"
        ),
        InlineKeyboardButton(
            text=f"{get_text('buttons.cancel', language)}",
            callback_data="roles_cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_specializations_selection_keyboard(user_specializations: List[str], language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора специализаций с чекбоксами
    
    Args:
        user_specializations: Текущие специализации пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup для выбора специализаций
    """
    buttons = []
    
    # Импортируем список доступных специализаций
    from uk_management_bot.services.specialization_service import SpecializationService
    available = SpecializationService.AVAILABLE_SPECIALIZATIONS
    
    # Группируем по 2 в ряд для компактности
    for i in range(0, len(available), 2):
        row = []
        
        for j in range(2):
            if i + j < len(available):
                spec = available[i + j]
                is_selected = spec in user_specializations
                
                # Эмодзи для статуса
                checkbox = "☑️" if is_selected else "☐"
                spec_name = get_text(f"specializations.{spec}", language)
                
                row.append(InlineKeyboardButton(
                    text=f"{checkbox} {spec_name}",
                    callback_data=f"spec_toggle_{spec}"
                ))
        
        buttons.append(row)
    
    # Кнопки управления
    buttons.append([
        InlineKeyboardButton(
            text=get_text('buttons.save', language),
            callback_data="spec_save"
        ),
        InlineKeyboardButton(
            text=f"{get_text('buttons.cancel', language)}",
            callback_data="spec_cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_search_filters_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура фильтров для поиска пользователей
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с фильтрами
    """
    buttons = [
        # Фильтры по статусу
        [InlineKeyboardButton(
            text=f"📝 {get_text('filters.by_status', language)}",
            callback_data="search_filter_status"
        )],
        [InlineKeyboardButton(
            text=f"👥 {get_text('filters.by_role', language)}",
            callback_data="search_filter_role"
        )],
        [InlineKeyboardButton(
            text=f"🛠️ {get_text('filters.by_specialization', language)}",
            callback_data="search_filter_specialization"
        )],
        
        # Поиск по имени
        [InlineKeyboardButton(
            text=f"🔍 {get_text('search.by_name', language)}",
            callback_data="search_by_name"
        )],
        
        # Сброс фильтров и назад
        [InlineKeyboardButton(
            text=f"🔄 {get_text('buttons.reset_filters', language)}",
            callback_data="search_reset_filters"
        )],
        [InlineKeyboardButton(
            text=get_text('buttons.back', language),
            callback_data="user_mgmt_main"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirmation_keyboard(action: str, user_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения действия
    
    Args:
        action: Тип действия (approve, block, unblock)
        user_id: ID пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с подтверждением
    """
    buttons = [
        [
            InlineKeyboardButton(
                text=f"✅ {get_text('buttons.confirm', language)}",
                callback_data=f"confirm_{action}_{user_id}"
            ),
            InlineKeyboardButton(
                text=f"{get_text('buttons.cancel', language)}",
                callback_data=f"user_mgmt_user_{user_id}"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Простая клавиатура отмены для FSM состояний
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с кнопкой отмены
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{get_text('buttons.cancel', language)}",
            callback_data="user_mgmt_cancel"
        )]
    ])


def get_specialization_stats_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура для статистики специализаций
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup для управления специализациями
    """
    buttons = [
        [InlineKeyboardButton(
            text=f"🔍 {get_text('specializations.search_by_spec', language)}",
            callback_data="spec_search"
        )],
        [InlineKeyboardButton(
            text=f"📊 {get_text('specializations.view_stats', language)}",
            callback_data="spec_stats"
        )],
        [InlineKeyboardButton(
            text=get_text('buttons.back', language),
            callback_data="user_mgmt_main"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ═══

def _format_user_name(user) -> str:
    """Форматировать имя пользователя для отображения"""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not name:
        name = user.username or f"ID{user.telegram_id}"
    
    # Ограничиваем длину для красивого отображения
    if len(name) > 25:
        name = name[:22] + "..."
    
    return name


def _get_status_emoji(status: str) -> str:
    """Получить эмодзи для статуса пользователя"""
    status_emojis = {
        "pending": "📝",
        "approved": "✅",
        "blocked": "🚫"
    }
    return status_emojis.get(status, "❓")


def get_pagination_info(page: int, total_pages: int, total_items: int, language: str = 'ru') -> str:
    """
    Получить информацию о пагинации для отображения
    
    Args:
        page: Текущая страница
        total_pages: Общее количество страниц
        total_items: Общее количество элементов
        language: Язык интерфейса
        
    Returns:
        Отформатированная строка с информацией о пагинации
    """
    if total_items == 0:
        return get_text('pagination.no_items', language)
    
    return get_text('pagination.info', language).format(
        page=page,
        total_pages=total_pages,
        total_items=total_items
    )
