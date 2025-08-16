from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_manager_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🆕 Новые заявки"))
    builder.add(KeyboardButton(text="🔄 Активные заявки"))
    builder.add(KeyboardButton(text="💰 Закуп"))
    builder.add(KeyboardButton(text="📦 Архив"))
    builder.add(KeyboardButton(text="👥 Смены"))
    builder.add(KeyboardButton(text="👤 Сотрудники"))
    builder.add(KeyboardButton(text="👥 Управление пользователями"))  # Новая кнопка
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


