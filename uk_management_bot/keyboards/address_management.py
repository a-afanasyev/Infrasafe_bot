"""
Клавиатуры для управления справочником адресов
"""
from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from uk_management_bot.database.models import Yard, Building, Apartment, UserApartment


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ АДРЕСАМИ
# ═══════════════════════════════════════════════════════════════════════════════

def get_address_management_menu() -> InlineKeyboardMarkup:
    """Главное меню управления справочником адресов"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🏘 Управление дворами", callback_data="addr_yards_list")
    )
    builder.row(
        InlineKeyboardButton(text="🏢 Управление зданиями", callback_data="addr_buildings_list")
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Управление квартирами", callback_data="addr_apartments_list")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Модерация заявок", callback_data="addr_moderation_list")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="addr_stats")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu")
    )

    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# ДВОРЫ
# ═══════════════════════════════════════════════════════════════════════════════

def get_yards_menu() -> InlineKeyboardMarkup:
    """Меню управления дворами"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="➕ Добавить двор", callback_data="addr_yard_create")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список дворов", callback_data="addr_yards_list")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
    )

    return builder.as_markup()


def get_yards_list_keyboard(yards: List[Yard], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком дворов (с пагинацией)

    Args:
        yards: Список дворов
        page: Текущая страница (начиная с 0)
        page_size: Количество элементов на странице
    """
    builder = InlineKeyboardBuilder()

    start_idx = page * page_size
    end_idx = start_idx + page_size
    yards_page = yards[start_idx:end_idx]

    # Список дворов
    for yard in yards_page:
        status_icon = "✅" if yard.is_active else "❌"
        buildings_info = f" ({yard.buildings_count} зд.)" if hasattr(yard, 'buildings_count') else ""

        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {yard.name}{buildings_info}",
                callback_data=f"addr_yard_view:{yard.id}"
            )
        )

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"addr_yards_page:{page - 1}")
        )
    if end_idx < len(yards):
        pagination_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"addr_yards_page:{page + 1}")
        )

    if pagination_buttons:
        builder.row(*pagination_buttons)

    # Управление
    builder.row(
        InlineKeyboardButton(text="➕ Добавить двор", callback_data="addr_yard_create")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
    )

    return builder.as_markup()


def get_yard_details_keyboard(yard_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра двора"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"addr_yard_edit:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🏢 Здания", callback_data=f"addr_buildings_by_yard:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"addr_yard_delete:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ К списку дворов", callback_data="addr_yards_list")
    )

    return builder.as_markup()


def get_yard_edit_keyboard(yard_id: int) -> InlineKeyboardMarkup:
    """Клавиатура редактирования двора"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📝 Название", callback_data=f"addr_yard_edit_name:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📄 Описание", callback_data=f"addr_yard_edit_desc:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📍 GPS координаты", callback_data=f"addr_yard_edit_gps:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Активность", callback_data=f"addr_yard_toggle:{yard_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"addr_yard_view:{yard_id}")
    )

    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def get_buildings_menu() -> InlineKeyboardMarkup:
    """Меню управления зданиями"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="➕ Добавить здание", callback_data="addr_building_create")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список зданий", callback_data="addr_buildings_list")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
    )

    return builder.as_markup()


def get_buildings_list_keyboard(
    buildings: List[Building],
    page: int = 0,
    page_size: int = 10,
    yard_id: Optional[int] = None
) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком зданий (с пагинацией)

    Args:
        buildings: Список зданий
        page: Текущая страница
        page_size: Количество элементов на странице
        yard_id: ID двора (если фильтруем по двору)
    """
    builder = InlineKeyboardBuilder()

    start_idx = page * page_size
    end_idx = start_idx + page_size
    buildings_page = buildings[start_idx:end_idx]

    # Список зданий
    for building in buildings_page:
        status_icon = "✅" if building.is_active else "❌"
        apartments_info = f" ({building.apartments_count} кв.)" if hasattr(building, 'apartments_count') else ""

        # Обрезаем длинный адрес
        address_short = building.address[:40] + "..." if len(building.address) > 40 else building.address

        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {address_short}{apartments_info}",
                callback_data=f"addr_building_view:{building.id}"
            )
        )

    # Пагинация
    pagination_buttons = []
    callback_prefix = f"addr_buildings_by_yard_page:{yard_id}" if yard_id else "addr_buildings_page"

    if page > 0:
        pagination_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"{callback_prefix}:{page - 1}")
        )
    if end_idx < len(buildings):
        pagination_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"{callback_prefix}:{page + 1}")
        )

    if pagination_buttons:
        builder.row(*pagination_buttons)

    # Управление
    builder.row(
        InlineKeyboardButton(text="➕ Добавить здание", callback_data="addr_building_create")
    )

    # Кнопка "Назад" зависит от контекста
    if yard_id:
        builder.row(
            InlineKeyboardButton(text="◀️ К двору", callback_data=f"addr_yard_view:{yard_id}")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
        )

    return builder.as_markup()


def get_building_details_keyboard(building_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра здания"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"addr_building_edit:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Квартиры", callback_data=f"addr_apartments_by_building:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔢 Автозаполнение квартир", callback_data=f"addr_building_autofill:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"addr_building_delete:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ К списку зданий", callback_data="addr_buildings_list")
    )

    return builder.as_markup()


def get_building_edit_keyboard(building_id: int) -> InlineKeyboardMarkup:
    """Клавиатура редактирования здания"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📝 Адрес", callback_data=f"addr_building_edit_addr:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🏘 Двор", callback_data=f"addr_building_edit_yard:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📍 GPS координаты", callback_data=f"addr_building_edit_gps:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🚪 Подъезды", callback_data=f"addr_building_edit_entrances:{building_id}"),
        InlineKeyboardButton(text="🏗 Этажи", callback_data=f"addr_building_edit_floors:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📄 Описание", callback_data=f"addr_building_edit_desc:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Активность", callback_data=f"addr_building_toggle:{building_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"addr_building_view:{building_id}")
    )

    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

def get_apartments_menu() -> InlineKeyboardMarkup:
    """Меню управления квартирами"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="addr_apartment_create")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список квартир", callback_data="addr_apartments_list")
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Поиск квартиры", callback_data="addr_apartment_search")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
    )

    return builder.as_markup()


def get_apartments_list_keyboard(
    apartments: List[Apartment],
    page: int = 0,
    page_size: int = 10,
    building_id: Optional[int] = None
) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком квартир (с пагинацией)

    Args:
        apartments: Список квартир
        page: Текущая страница
        page_size: Количество элементов на странице
        building_id: ID здания (если фильтруем по зданию)
    """
    builder = InlineKeyboardBuilder()

    start_idx = page * page_size
    end_idx = start_idx + page_size
    apartments_page = apartments[start_idx:end_idx]

    # Список квартир
    for apartment in apartments_page:
        status_icon = "✅" if apartment.is_active else "❌"
        residents_info = ""

        if hasattr(apartment, 'residents_count'):
            residents_info = f" ({apartment.residents_count} жит.)"

        # Полный адрес или короткий
        if hasattr(apartment, 'full_address'):
            address = apartment.full_address[:50] + "..." if len(apartment.full_address) > 50 else apartment.full_address
        else:
            address = f"Квартира {apartment.apartment_number}"

        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {address}{residents_info}",
                callback_data=f"addr_apartment_view:{apartment.id}"
            )
        )

    # Пагинация
    pagination_buttons = []
    callback_prefix = f"addr_apartments_by_building_page:{building_id}" if building_id else "addr_apartments_page"

    if page > 0:
        pagination_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"{callback_prefix}:{page - 1}")
        )
    if end_idx < len(apartments):
        pagination_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"{callback_prefix}:{page + 1}")
        )

    if pagination_buttons:
        builder.row(*pagination_buttons)

    # Управление
    builder.row(
        InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="addr_apartment_create")
    )

    # Кнопка "Назад" зависит от контекста
    if building_id:
        builder.row(
            InlineKeyboardButton(text="◀️ К зданию", callback_data=f"addr_building_view:{building_id}")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
        )

    return builder.as_markup()


def get_apartment_details_keyboard(apartment_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра квартиры"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"addr_apartment_edit:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="👥 Жители", callback_data=f"addr_apartment_residents:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"addr_apartment_delete:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ К списку квартир", callback_data="addr_apartments_list")
    )

    return builder.as_markup()


def get_apartment_edit_keyboard(apartment_id: int) -> InlineKeyboardMarkup:
    """Клавиатура редактирования квартиры"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🔢 Номер", callback_data=f"addr_apartment_edit_number:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🏢 Здание", callback_data=f"addr_apartment_edit_building:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🚪 Подъезд", callback_data=f"addr_apartment_edit_entrance:{apartment_id}"),
        InlineKeyboardButton(text="🏗 Этаж", callback_data=f"addr_apartment_edit_floor:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🛏 Комнаты", callback_data=f"addr_apartment_edit_rooms:{apartment_id}"),
        InlineKeyboardButton(text="📐 Площадь", callback_data=f"addr_apartment_edit_area:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📄 Описание", callback_data=f"addr_apartment_edit_desc:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Активность", callback_data=f"addr_apartment_toggle:{apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"addr_apartment_view:{apartment_id}")
    )

    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# МОДЕРАЦИЯ ЗАЯВОК
# ═══════════════════════════════════════════════════════════════════════════════

def get_moderation_menu() -> InlineKeyboardMarkup:
    """Меню модерации заявок на квартиры"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📋 Заявки на рассмотрении", callback_data="addr_moderation_list")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
    )

    return builder.as_markup()


def get_moderation_requests_keyboard(
    requests: List[UserApartment],
    page: int = 0,
    page_size: int = 10
) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком заявок на модерацию

    Args:
        requests: Список заявок UserApartment со статусом pending
        page: Текущая страница
        page_size: Количество элементов на странице
    """
    builder = InlineKeyboardBuilder()

    start_idx = page * page_size
    end_idx = start_idx + page_size
    requests_page = requests[start_idx:end_idx]

    # Список заявок
    for req in requests_page:
        user_name = f"{req.user.first_name or ''} {req.user.last_name or ''}".strip()
        if not user_name:
            user_name = f"ID: {req.user.telegram_id}"

        apartment_info = f"кв. {req.apartment.apartment_number}"
        if req.apartment.building:
            building_short = req.apartment.building.address[:30] + "..." if len(req.apartment.building.address) > 30 else req.apartment.building.address
            apartment_info = f"{apartment_info}, {building_short}"

        # Время подачи заявки
        days_ago = (req.requested_at.date() - req.requested_at.date()).days if req.requested_at else 0
        time_info = f" ({days_ago}д)" if days_ago > 0 else ""

        builder.row(
            InlineKeyboardButton(
                text=f"👤 {user_name} → {apartment_info}{time_info}",
                callback_data=f"addr_moderation_view:{req.id}"
            )
        )

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"addr_moderation_page:{page - 1}")
        )
    if end_idx < len(requests):
        pagination_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"addr_moderation_page:{page + 1}")
        )

    if pagination_buttons:
        builder.row(*pagination_buttons)

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
    )

    return builder.as_markup()


def get_moderation_request_details_keyboard(user_apartment_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра заявки"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"addr_moderation_approve:{user_apartment_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"addr_moderation_reject:{user_apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="👤 Профиль пользователя", callback_data=f"user_profile:{user_apartment_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ К списку заявок", callback_data="addr_moderation_list")
    )

    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# ПОЛЬЗОВАТЕЛЬСКИЕ КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════════════════════

def get_user_apartment_selection_keyboard(
    items: List,
    item_type: str,
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """
    Универсальная клавиатура для выбора двора/здания/квартиры пользователем

    Args:
        items: Список объектов (Yard, Building или Apartment)
        item_type: Тип объекта ("yard", "building", "apartment")
        callback_prefix: Префикс для callback_data
    """
    builder = InlineKeyboardBuilder()

    for item in items:
        if item_type == "yard":
            text = item.name
            value = item.id
        elif item_type == "building":
            text = item.address[:50] + "..." if len(item.address) > 50 else item.address
            value = item.id
        elif item_type == "apartment":
            text = f"Квартира {item.apartment_number}"
            if hasattr(item, 'floor') and item.floor:
                text += f", {item.floor} этаж"
            if hasattr(item, 'entrance') and item.entrance:
                text += f", подъезд {item.entrance}"
            value = item.id
        else:
            continue

        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"{callback_prefix}:{value}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_apartment_selection")
    )

    return builder.as_markup()


def get_my_apartments_keyboard(user_apartments: List[UserApartment]) -> InlineKeyboardMarkup:
    """Клавиатура со списком квартир пользователя"""
    builder = InlineKeyboardBuilder()

    for ua in user_apartments:
        status_icon = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }.get(ua.status, '❓')

        primary_icon = '⭐' if ua.is_primary else ''
        owner_icon = '👑' if ua.is_owner else ''

        text = f"{status_icon}{primary_icon}{owner_icon} {ua.apartment.full_address if hasattr(ua.apartment, 'full_address') else f'Квартира {ua.apartment.apartment_number}'}"

        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"my_apartment_view:{ua.id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="add_my_apartment")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="profile_menu")
    )

    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# ОБЩИЕ КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════════════════════

def get_confirmation_keyboard(confirm_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    """Универсальная клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=confirm_callback),
        InlineKeyboardButton(text="❌ Нет", callback_data=cancel_callback)
    )

    return builder.as_markup()


def get_skip_or_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопками Пропустить и Отмена"""
    builder = ReplyKeyboardBuilder()

    builder.row(
        KeyboardButton(text="⏭ Пропустить"),
        KeyboardButton(text="❌ Отмена")
    )

    return builder.as_markup(resize_keyboard=True)


def get_cancel_keyboard_inline() -> InlineKeyboardMarkup:
    """Inline-клавиатура с кнопкой отмены"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")
    )

    return builder.as_markup()
