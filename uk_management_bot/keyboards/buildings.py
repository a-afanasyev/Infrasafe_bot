"""Building Selection Keyboards.

Week 2, Task 5.2: Building Selection Keyboards
Keyboards for building directory integration in bot.
"""

from typing import List, Dict, Any, Optional
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_city_selection_keyboard(cities: List[str]) -> ReplyKeyboardMarkup:
    """Create keyboard for city selection.

    Args:
        cities: List of city names

    Returns:
        ReplyKeyboardMarkup with cities
    """
    builder = ReplyKeyboardBuilder()

    # Add city buttons (2 per row)
    for city in cities:
        builder.button(text=f"📍 {city}")

    # Add cancel button
    builder.button(text="❌ Отмена")

    # Arrange in rows (2 cities per row)
    builder.adjust(2)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выберите город"
    )


def get_building_search_keyboard() -> ReplyKeyboardMarkup:
    """Create keyboard for building search.

    Returns:
        ReplyKeyboardMarkup with search options
    """
    builder = ReplyKeyboardBuilder()

    builder.button(text="🔍 Начать поиск")
    builder.button(text="✏️ Ввести адрес вручную")
    builder.button(text="❌ Отмена")

    builder.adjust(1)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Введите улицу и номер дома"
    )


def get_building_list_inline_keyboard(
    buildings: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """Create inline keyboard for building list (paginated).

    Args:
        buildings: List of building dicts
        page: Current page number
        total_pages: Total number of pages

    Returns:
        InlineKeyboardMarkup with building buttons
    """
    builder = InlineKeyboardBuilder()

    # Add building buttons
    for building in buildings:
        building_id = building['id']
        full_address = building['full_address']

        # Shorten address for button (max 40 chars)
        display_address = full_address
        if len(display_address) > 40:
            display_address = display_address[:37] + "..."

        # Add emoji based on building type
        building_type = building.get('building_type', '')
        emoji = {
            'residential': '🏠',
            'commercial': '🏢',
            'mixed': '🏘️',
            'industrial': '🏭',
            'other': '🏗️'
        }.get(building_type, '📍')

        builder.button(
            text=f"{emoji} {display_address}",
            callback_data=f"building_select:{building_id}"
        )

    # Arrange 1 building per row
    builder.adjust(1)

    # Add pagination if needed
    if total_pages > 1:
        pagination_row = []

        if page > 1:
            pagination_row.append(InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"building_page:{page - 1}"
            ))

        pagination_row.append(InlineKeyboardButton(
            text=f"📄 {page}/{total_pages}",
            callback_data="building_page_info"
        ))

        if page < total_pages:
            pagination_row.append(InlineKeyboardButton(
                text="Вперёд ▶️",
                callback_data=f"building_page:{page + 1}"
            ))

        builder.row(*pagination_row)

    # Add action buttons
    builder.row(
        InlineKeyboardButton(
            text="🔍 Новый поиск",
            callback_data="building_new_search"
        ),
        InlineKeyboardButton(
            text="✏️ Ввести вручную",
            callback_data="building_manual_entry"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="building_cancel"
        )
    )

    return builder.as_markup()


def get_building_confirmation_keyboard(building_id: str) -> InlineKeyboardMarkup:
    """Create keyboard for building selection confirmation.

    Args:
        building_id: Building UUID

    Returns:
        InlineKeyboardMarkup with confirm/cancel buttons
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Подтвердить",
        callback_data=f"building_confirm:{building_id}"
    )
    builder.button(
        text="🔍 Другое здание",
        callback_data="building_choose_another"
    )
    builder.button(
        text="❌ Отмена",
        callback_data="building_cancel"
    )

    builder.adjust(1)

    return builder.as_markup()


def get_address_details_keyboard() -> ReplyKeyboardMarkup:
    """Create keyboard for entering address details (apartment/entrance/floor).

    Returns:
        ReplyKeyboardMarkup with options
    """
    builder = ReplyKeyboardBuilder()

    builder.button(text="➡️ Пропустить")
    builder.button(text="❌ Отмена")

    builder.adjust(1)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Квартира, подъезд, этаж (необязательно)"
    )


def get_building_admin_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for building admin panel.

    Returns:
        InlineKeyboardMarkup with admin options
    """
    builder = InlineKeyboardBuilder()

    builder.button(text="📋 Список зданий", callback_data="building_admin_list")
    builder.button(text="➕ Добавить здание", callback_data="building_admin_create")
    builder.button(text="📊 Статистика", callback_data="building_admin_stats")
    builder.button(text="🔍 Поиск", callback_data="building_admin_search")
    builder.button(text="🔙 Назад", callback_data="building_admin_back")

    builder.adjust(2)

    return builder.as_markup()


def get_building_details_keyboard(building_id: str) -> InlineKeyboardMarkup:
    """Create keyboard for building details view.

    Args:
        building_id: Building UUID

    Returns:
        InlineKeyboardMarkup with action buttons
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✏️ Редактировать",
        callback_data=f"building_edit:{building_id}"
    )
    builder.button(
        text="🗑️ Удалить",
        callback_data=f"building_delete:{building_id}"
    )
    builder.button(
        text="🔙 К списку",
        callback_data="building_admin_list"
    )

    builder.adjust(2, 1)

    return builder.as_markup()


def get_manual_address_fallback_keyboard() -> ReplyKeyboardMarkup:
    """Create keyboard for manual address entry fallback.

    Returns:
        ReplyKeyboardMarkup with cancel option
    """
    builder = ReplyKeyboardBuilder()

    builder.button(text="🔙 Вернуться к поиску")
    builder.button(text="❌ Отмена")

    builder.adjust(1)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Введите полный адрес"
    )


# Helper functions

def format_building_info(building: Dict[str, Any]) -> str:
    """Format building info for display in message.

    Args:
        building: Building data dict

    Returns:
        Formatted string with building details
    """
    lines = []

    # Header with emoji
    building_type = building.get('building_type', '')
    emoji = {
        'residential': '🏠',
        'commercial': '🏢',
        'mixed': '🏘️',
        'industrial': '🏭',
        'other': '🏗️'
    }.get(building_type, '📍')

    lines.append(f"{emoji} <b>Здание</b>")
    lines.append("")

    # Address
    lines.append(f"📍 <b>Адрес:</b> {building['full_address']}")

    # Details
    if building.get('building_type'):
        type_names = {
            'residential': 'Жилое',
            'commercial': 'Коммерческое',
            'mixed': 'Смешанное',
            'industrial': 'Промышленное',
            'other': 'Другое'
        }
        type_name = type_names.get(building['building_type'], building['building_type'])
        lines.append(f"🏗️ <b>Тип:</b> {type_name}")

    if building.get('floors_count'):
        lines.append(f"📏 <b>Этажей:</b> {building['floors_count']}")

    if building.get('entrance_count'):
        lines.append(f"🚪 <b>Подъездов:</b> {building['entrance_count']}")

    if building.get('apartments_count'):
        lines.append(f"🏘️ <b>Квартир:</b> {building['apartments_count']}")

    if building.get('year_built'):
        lines.append(f"📅 <b>Год постройки:</b> {building['year_built']}")

    # Coordinates
    if building.get('coordinates'):
        coords = building['coordinates']
        lines.append("")
        lines.append(f"🗺️ <b>Координаты:</b>")
        lines.append(f"   • Широта: {coords['lat']:.6f}")
        lines.append(f"   • Долгота: {coords['lon']:.6f}")

    # Notes
    if building.get('notes'):
        lines.append("")
        lines.append(f"📝 <b>Примечания:</b>")
        lines.append(f"{building['notes']}")

    return "\n".join(lines)


def format_building_list_message(
    buildings: List[Dict[str, Any]],
    total: int,
    page: int,
    search_query: Optional[str] = None
) -> str:
    """Format building list message.

    Args:
        buildings: List of buildings
        total: Total number of buildings
        page: Current page
        search_query: Search query if applicable

    Returns:
        Formatted message string
    """
    lines = []

    if search_query:
        lines.append(f"🔍 <b>Результаты поиска:</b> \"{search_query}\"")
    else:
        lines.append("📋 <b>Список зданий</b>")

    lines.append("")
    lines.append(f"Найдено: {total}")
    lines.append("")
    lines.append("Выберите здание из списка ниже:")

    return "\n".join(lines)
