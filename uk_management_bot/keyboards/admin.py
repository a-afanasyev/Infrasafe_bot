from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_manager_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🆕 Новые заявки"))
    builder.add(KeyboardButton(text="🔄 Активные заявки"))
    builder.add(KeyboardButton(text="💰 Закуп"))
    builder.add(KeyboardButton(text="📦 Архив"))
    builder.add(KeyboardButton(text="👥 Смены"))
    builder.add(KeyboardButton(text="👥 Управление пользователями"))
    builder.add(KeyboardButton(text="👷 Управление сотрудниками"))
    builder.add(KeyboardButton(text="📨 Создать приглашение"))  # Кнопка для создания приглашений
    builder.add(KeyboardButton(text="🔙 Назад"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_manager_requests_inline(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.add(InlineKeyboardButton(text="◀️", callback_data=f"mreq_page_{page-1}"))
    builder.add(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="mreq_page_curr"))
    if page < total_pages:
        builder.add(InlineKeyboardButton(text="▶️", callback_data=f"mreq_page_{page+1}"))
    builder.adjust(3)
    return builder.as_markup()


def _status_icon(status: str) -> str:
    mapping = {
        "В работе": "🛠️",
        "Закуп": "💰",
        "Уточнение": "❓",
        "Подтверждена": "⭐",
        "Отменена": "❌",
        "Выполнена": "✅",
        "Новая": "🆕",
    }
    return mapping.get(status, "")


def get_manager_request_list_kb(requests: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Список заявок: кнопки "#id • Категория" и пагинация."""
    builder = InlineKeyboardBuilder()
    for item in requests:
        short_addr = item.get('address', '')[:40]
        if len(item.get('address', '')) > 40:
            short_addr += '…'
        icon = _status_icon(item.get('status', ''))
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} #{item['id']} • {item['category']} • {short_addr}",
                callback_data=f"mview_{item['id']}"
            )
        )
    # Пагинация
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"mreq_page_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="mreq_page_curr"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"mreq_page_{page+1}"))
    if nav:
        builder.row(*nav)
    return builder.as_markup()


def get_invite_role_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора роли для приглашения"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="👤 Заявитель", callback_data="invite_role_applicant"))
    builder.add(InlineKeyboardButton(text="🛠️ Исполнитель", callback_data="invite_role_executor"))
    builder.add(InlineKeyboardButton(text="👨‍💼 Менеджер", callback_data="invite_role_manager"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="invite_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_invite_specialization_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора специализации для исполнителя"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔧 Сантехник", callback_data="invite_spec_plumber"))
    builder.add(InlineKeyboardButton(text="⚡ Электрик", callback_data="invite_spec_electrician"))
    builder.add(InlineKeyboardButton(text="🌡️ Отопление/вентиляция", callback_data="invite_spec_hvac"))
    builder.add(InlineKeyboardButton(text="🧹 Уборка", callback_data="invite_spec_cleaning"))
    builder.add(InlineKeyboardButton(text="🔒 Охрана", callback_data="invite_spec_security"))
    builder.add(InlineKeyboardButton(text="🔧 Обслуживание", callback_data="invite_spec_maintenance"))
    builder.add(InlineKeyboardButton(text="🌳 Благоустройство", callback_data="invite_spec_landscaping"))
    builder.add(InlineKeyboardButton(text="🔨 Ремонт", callback_data="invite_spec_repair"))
    builder.add(InlineKeyboardButton(text="📦 Установка", callback_data="invite_spec_installation"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="invite_cancel"))
    builder.adjust(2)
    return builder.as_markup()


def get_invite_expiry_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора срока действия приглашения"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⏰ 1 час", callback_data="invite_expiry_1h"))
    builder.add(InlineKeyboardButton(text="📅 24 часа", callback_data="invite_expiry_24h"))
    builder.add(InlineKeyboardButton(text="📆 7 дней", callback_data="invite_expiry_7d"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="invite_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_invite_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания приглашения"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Создать приглашение", callback_data="invite_confirm"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="invite_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_user_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для одобрения/отклонения пользователя"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_user_{user_id}"))
    builder.add(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_user_{user_id}"))
    builder.add(InlineKeyboardButton(text="👁️ Просмотреть профиль", callback_data=f"view_user_{user_id}"))
    builder.adjust(2)
    return builder.as_markup()


