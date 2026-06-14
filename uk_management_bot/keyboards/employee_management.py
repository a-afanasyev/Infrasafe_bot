"""
Клавиатуры для управления сотрудниками

Содержит inline-клавиатуры для:
- Главного меню панели управления сотрудниками
- Списков сотрудников с пагинацией
- Действий с сотрудниками
- Выбора ролей и специализаций
"""

from typing import Dict
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.utils.helpers import get_text


def get_employee_management_main_keyboard(stats: Dict[str, int], language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Главное меню панели управления сотрудниками
    
    Args:
        stats: Статистика сотрудников
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с главным меню
    """
    buttons = [
        # Статистика
        [InlineKeyboardButton(
            text=f"📊 {get_text('employee_management.stats', language)}",
            callback_data="employee_mgmt_stats"
        )],
        
        # Списки сотрудников с счетчиками
        [InlineKeyboardButton(
            text=f"📝 {get_text('employee_management.pending_employees', language)} ({stats.get('pending', 0)})",
            callback_data="employee_mgmt_list_pending_1"
        )],
        [InlineKeyboardButton(
            text=f"✅ {get_text('employee_management.active_employees', language)} ({stats.get('active', 0)})",
            callback_data="employee_mgmt_list_active_1"
        )],
        [InlineKeyboardButton(
            text=f"🚫 {get_text('employee_management.blocked_employees', language)} ({stats.get('blocked', 0)})",
            callback_data="employee_mgmt_list_blocked_1"
        )],
        [InlineKeyboardButton(
            text=f"🛠️ {get_text('employee_management.executors', language)} ({stats.get('executors', 0)})",
            callback_data="employee_mgmt_list_executors_1"
        )],
        [InlineKeyboardButton(
            text=f"👨‍💼 {get_text('employee_management.managers', language)} ({stats.get('managers', 0)})",
            callback_data="employee_mgmt_list_managers_1"
        )],
        
        # Поиск и специализации
        [InlineKeyboardButton(
            text=f"🔍 {get_text('employee_management.search', language)}",
            callback_data="employee_mgmt_search"
        )],
        [InlineKeyboardButton(
            text=f"🛠️ {get_text('employee_management.specializations', language)}",
            callback_data="employee_mgmt_specializations"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=get_text('buttons.back', language),
            callback_data="admin_panel"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_employee_list_keyboard(employees_data: Dict, list_type: str, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура списка сотрудников с пагинацией
    
    Args:
        employees_data: Данные сотрудников с пагинацией
        list_type: Тип списка (pending, active, blocked, executors, managers)
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup со списком сотрудников
    """
    buttons = []
    
    # Сотрудники (по 5 на страницу для удобства)
    for employee in employees_data.get('employees', []):
        employee_name = _format_employee_name(employee)
        status_emoji = _get_status_emoji(employee.status)
        
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} {employee_name}",
            callback_data=f"employee_mgmt_employee_{employee.id}"
        )])
    
    # Если сотрудников нет
    if not employees_data.get('employees'):
        buttons.append([InlineKeyboardButton(
            text=get_text('employee_management.no_employees', language),
            callback_data="no_action"
        )])
    
    # Пагинация
    current_page = employees_data.get('current_page', 1)
    total_pages = employees_data.get('total_pages', 1)
    
    if total_pages > 1:
        nav_buttons = []
        
        if current_page > 1:
            nav_buttons.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"employee_mgmt_list_{list_type}_{current_page - 1}"
            ))
        
        nav_buttons.append(InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data="no_action"
        ))
        
        if current_page < total_pages:
            nav_buttons.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"employee_mgmt_list_{list_type}_{current_page + 1}"
            ))
        
        buttons.append(nav_buttons)
    
    # Кнопка "Назад"
    buttons.append([InlineKeyboardButton(
        text=get_text('buttons.back', language),
        callback_data="employee_mgmt_main"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_employee_actions_keyboard(employee_id: int, status: str, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура действий с сотрудником
    
    Args:
        employee_id: ID сотрудника
        status: Статус сотрудника
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с действиями
    """
    buttons = []
    
    # Действия в зависимости от статуса
    if status == "pending":
        buttons.extend([
            [InlineKeyboardButton(
                text=f"✅ {get_text('employee_management.approve', language)}",
                callback_data=f"approve_employee_{employee_id}"
            )],
            [InlineKeyboardButton(
                text=f"❌ {get_text('employee_management.reject', language)}",
                callback_data=f"reject_employee_{employee_id}"
            )]
        ])
    elif status == "approved":
        buttons.extend([
            [InlineKeyboardButton(
                text=f"🚫 {get_text('employee_management.block', language)}",
                callback_data=f"block_employee_{employee_id}"
            )],
            [InlineKeyboardButton(
                text=f"🛠️ {get_text('employee_management.change_role', language)}",
                callback_data=f"change_employee_role_{employee_id}"
            )],
            [InlineKeyboardButton(
                text=f"🔧 {get_text('employee_management.specialization', language)}",
                callback_data=f"change_employee_specialization_{employee_id}"
            )]
        ])
    elif status == "blocked":
        buttons.extend([
            [InlineKeyboardButton(
                text=f"✅ {get_text('employee_management.unblock', language)}",
                callback_data=f"unblock_employee_{employee_id}"
            )]
        ])
    
    # Общие действия
    buttons.extend([
        [InlineKeyboardButton(
            text=f"🗑️ {get_text('employee_management.delete', language)}",
            callback_data=f"delete_employee_{employee_id}"
        )],
        [InlineKeyboardButton(
            text=f"📝 {get_text('employee_management.edit', language)}",
            callback_data=f"edit_employee_{employee_id}"
        )]
    ])
    
    # Кнопка "Назад"
    buttons.append([InlineKeyboardButton(
        text=get_text('buttons.back', language),
        callback_data="employee_mgmt_main"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_roles_management_keyboard(selected_roles: list = None, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура управления ролями с галочками
    
    Args:
        selected_roles: Список выбранных ролей
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с ролями
    """
    if selected_roles is None:
        selected_roles = []
    
    buttons = []
    
    # Роли с галочками
    roles = [
        ('executor', '🛠️', get_text('employee_management.keyboards.role_executor', language=language)),
        ('manager', '👨‍💼', get_text('employee_management.keyboards.role_manager', language=language)),
        ('inspector', '🚶', get_text('employee_management.keyboards.role_inspector', language=language)),
        ('applicant', '👤', get_text('employee_management.keyboards.role_applicant', language=language))
    ]

    for role_key, role_emoji, role_name in roles:
        is_selected = role_key in selected_roles
        checkbox = "✅" if is_selected else "⬜"
        buttons.append([InlineKeyboardButton(
            text=f"{checkbox} {role_emoji} {role_name}",
            callback_data=f"role_toggle_{role_key}"
        )])
    
    # Кнопки действий
    buttons.append([
        InlineKeyboardButton(
            text=get_text('buttons.save', language),
            callback_data="role_save"
        ),
        InlineKeyboardButton(
            text=f"{get_text('buttons.cancel', language)}",
            callback_data="role_cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_specializations_selection_keyboard(selected_specializations: list = None, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора специализаций с галочками
    
    Args:
        selected_specializations: Список выбранных специализаций
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup со специализациями
    """
    if selected_specializations is None:
        selected_specializations = []
    
    buttons = []

    # MGR-07: единый источник специализаций — SpecializationService.AVAILABLE_SPECIALIZATIONS
    # (10 ключей, вкл. 'general') + namespace specializations.{spec}, как в
    # keyboards/user_management.py. Раньше здесь был отдельный хардкод из 9 (без
    # 'general') с namespace employee_management.keyboards.spec_* — рассинхрон меток.
    from uk_management_bot.services.specialization_service import SpecializationService

    for spec_key in SpecializationService.AVAILABLE_SPECIALIZATIONS:
        is_selected = spec_key in selected_specializations
        checkbox = "✅" if is_selected else "⬜"
        spec_name = get_text(f"specializations.{spec_key}", language=language)
        buttons.append([InlineKeyboardButton(
            text=f"{checkbox} {spec_name}",
            callback_data=f"spec_toggle_{spec_key}"
        )])
    
    # Кнопки действий
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


def get_employee_edit_keyboard(employee_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура редактирования сотрудника (только текстовые поля)
    
    Args:
        employee_id: ID сотрудника
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с опциями редактирования
    """
    buttons = [
        [InlineKeyboardButton(
            text=f"📝 {get_text('employee_management.full_name', language)}",
            callback_data=f"edit_employee_name_{employee_id}"
        )],
        [InlineKeyboardButton(
            text=f"📱 {get_text('employee_management.phone', language)}",
            callback_data=f"edit_employee_phone_{employee_id}"
        )],
        [InlineKeyboardButton(
            text=get_text('buttons.back', language),
            callback_data=f"employee_mgmt_employee_{employee_id}"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура возврата в главное меню управления сотрудниками.

    BUG-BOT-011: переименовано из "Отмена" в "Назад" — callback
    `employee_mgmt_main` выполняет навигацию, без очистки FSM-состояния.
    Для FSM-flow с очисткой используется `❌ Отмена` (см. role_cancel,
    spec_cancel handlers с явным state-filter).

    Args:
        language: Язык интерфейса

    Returns:
        InlineKeyboardMarkup с кнопкой возврата.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_text('buttons.back', language),
            callback_data="employee_mgmt_main"
        )]
    ])


def get_confirmation_keyboard(action: str, employee_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения действия
    
    Args:
        action: Тип действия
        employee_id: ID сотрудника
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с подтверждением
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ {get_text('buttons.confirm', language)}",
            callback_data=f"confirm_{action}_{employee_id}"
        )],
        [InlineKeyboardButton(
            text=f"{get_text('buttons.cancel', language)}",
            callback_data="employee_mgmt_main"
        )]
    ])


# ═══ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ═══

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


def _get_status_emoji(status: str) -> str:
    """Возвращает эмодзи для статуса"""
    status_emojis = {
        "pending": "📝",
        "approved": "✅",
        "blocked": "🚫",
        "active": "✅",
        "inactive": "⏸️"
    }
    return status_emojis.get(status, "❓")
