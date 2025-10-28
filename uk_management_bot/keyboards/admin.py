from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from uk_management_bot.utils.request_helpers import RequestCallbackHelper


def get_manager_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🆕 Новые заявки"))
    builder.add(KeyboardButton(text="🔄 Активные заявки"))
    builder.add(KeyboardButton(text="✅ Исполненные заявки"))  # Новая кнопка для исполненных заявок
    builder.add(KeyboardButton(text="💰 Закуп"))
    builder.add(KeyboardButton(text="📦 Архив"))
    builder.add(KeyboardButton(text="👥 Смены"))
    builder.add(KeyboardButton(text="📍 Справочник адресов"))  # Новая кнопка для управления адресами
    builder.add(KeyboardButton(text="👥 Управление пользователями"))
    builder.add(KeyboardButton(text="👷 Управление сотрудниками"))
    builder.add(KeyboardButton(text="📨 Создать приглашение"))  # Кнопка для создания приглашений
    builder.add(KeyboardButton(text="🔙 Назад"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_completed_requests_submenu() -> ReplyKeyboardMarkup:
    """Подменю для раздела 'Исполненные заявки'"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📋 Ожидают проверки"))
    builder.add(KeyboardButton(text="🔄 Возвращённые"))
    builder.add(KeyboardButton(text="⏳ Не принятые"))
    builder.add(KeyboardButton(text="🔙 Назад в меню"))
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
    """Список заявок: кнопки "#номер • Категория" и пагинация."""
    builder = InlineKeyboardBuilder()
    for item in requests:
        short_addr = item.get('address', '')[:40]
        if len(item.get('address', '')) > 40:
            short_addr += '…'
        icon = _status_icon(item.get('status', ''))
        request_number = item.get('request_number', item.get('id', 'N/A'))
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} #{request_number} • {item['category']} • {short_addr}",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mview_", str(request_number))
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
    import logging
    logger = logging.getLogger(__name__)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_user_{user_id}"))
    builder.add(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_user_{user_id}"))
    builder.add(InlineKeyboardButton(text="👁️ Просмотреть профиль", callback_data=f"view_user_{user_id}"))
    builder.adjust(2)

    logger.info(f"🟢 Создана клавиатура одобрения для user_id={user_id}")
    logger.info(f"🟢 Кнопки: approve_user_{user_id}, reject_user_{user_id}, view_user_{user_id}")

    return builder.as_markup()


def get_manager_request_actions_keyboard(request_number: str, has_media: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура действий с заявкой для менеджеров

    Args:
        request_number: Номер заявки
        has_media: Есть ли прикрепленные медиафайлы к заявке
    """
    builder = InlineKeyboardBuilder()

    # Основные действия с заявкой - сокращенный текст для лучшей читаемости
    builder.add(InlineKeyboardButton(text="🔧 В работу", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("accept_", request_number)))
    builder.add(InlineKeyboardButton(text="❌ Отклонить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("deny_", request_number)))
    builder.add(InlineKeyboardButton(text="❓ Уточнить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("clarify_", request_number)))
    builder.add(InlineKeyboardButton(text="💰 В закуп", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("purchase_", request_number)))
    builder.add(InlineKeyboardButton(text="✅ Завершить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("complete_", request_number)))
    builder.add(InlineKeyboardButton(text="🗑️ Удалить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("delete_", request_number)))

    # Настройка расположения кнопок (2 кнопки в ряд для основных действий)
    builder.adjust(2)

    # Кнопка для просмотра медиафайлов - показывается только если есть медиа
    if has_media:
        builder.row(InlineKeyboardButton(text="📎 Медиа", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("media_", request_number)))

    return builder.as_markup()


def get_manager_completed_request_actions_keyboard(request_number: str, is_returned: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура действий с исполненной заявкой для менеджера

    Args:
        request_number: Номер заявки
        is_returned: Возвращена ли заявка заявителем
    """
    builder = InlineKeyboardBuilder()

    if is_returned:
        # Для возвратных заявок - показать другие действия
        builder.row(InlineKeyboardButton(
            text="✅ Подтвердить повторно",
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("reconfirm_completed_", request_number)
        ))
        builder.row(InlineKeyboardButton(
            text="🔄 Вернуть в работу",
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("return_to_work_", request_number)
        ))
    else:
        # Для обычных исполненных заявок
        builder.row(InlineKeyboardButton(
            text="✅ Подтвердить выполнение",
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("confirm_completed_", request_number)
        ))
        builder.row(InlineKeyboardButton(
            text="🔄 Вернуть в работу",
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("return_to_work_", request_number)
        ))

    return builder.as_markup()


def get_rating_keyboard(request_number: str) -> InlineKeyboardMarkup:
    """Клавиатура с оценками 1-5 звёзд для заявителя

    Args:
        request_number: Номер заявки
    """
    builder = InlineKeyboardBuilder()

    # Добавляем кнопки с оценками
    stars = [
        ("⭐", 1),
        ("⭐⭐", 2),
        ("⭐⭐⭐", 3),
        ("⭐⭐⭐⭐", 4),
        ("⭐⭐⭐⭐⭐", 5),
    ]

    for star_text, rating_value in stars:
        builder.row(InlineKeyboardButton(
            text=star_text,
            callback_data=f"rate_{request_number}_{rating_value}"
        ))

    return builder.as_markup()


def get_applicant_completed_request_actions_keyboard(request_number: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с выполненной заявкой для заявителя

    Args:
        request_number: Номер заявки
    """
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="✅ Принять заявку",
        callback_data=f"accept_request_{request_number}"
    ))
    builder.row(InlineKeyboardButton(
        text="❌ Вернуть заявку",
        callback_data=f"return_request_{request_number}"
    ))
    builder.row(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_pending_acceptance"
    ))

    return builder.as_markup()


def get_skip_media_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Пропустить' для медиа"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_return_media"))
    return builder.as_markup()


def get_assignment_type_keyboard(request_number: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа назначения исполнителя"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="👥 Дежурному специалисту",
        callback_data=f"assign_duty_{request_number}"
    ))

    builder.row(InlineKeyboardButton(
        text="👤 Конкретному исполнителю",
        callback_data=f"assign_specific_{request_number}"
    ))

    return builder.as_markup()


def get_executors_by_category_keyboard(request_number: str, category: str, executors: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком исполнителей для данной категории"""
    builder = InlineKeyboardBuilder()

    if not executors:
        builder.row(InlineKeyboardButton(
            text="❌ Нет доступных исполнителей",
            callback_data="no_executors"
        ))
    else:
        for executor in executors:
            # Формируем текст кнопки с информацией об исполнителе
            name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
            if not name:
                name = f"@{executor.username}" if executor.username else f"ID{executor.id}"

            # Добавляем статус смены если есть
            status_icon = "🟢" if hasattr(executor, 'on_shift') and executor.on_shift else "⚪"

            button_text = f"{status_icon} {name}"

            builder.row(InlineKeyboardButton(
                text=button_text,
                callback_data=f"assign_executor_{request_number}_{executor.id}"
            ))

    builder.row(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"back_to_assignment_type_{request_number}"
    ))

    return builder.as_markup()


def get_unaccepted_request_actions_keyboard(request_number: str) -> InlineKeyboardMarkup:
    """
    Клавиатура действий для непринятой заявки (для менеджера)

    Args:
        request_number: Номер заявки

    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    builder = InlineKeyboardBuilder()

    # Кнопка повторного уведомления заявителя
    builder.row(InlineKeyboardButton(
        text="🔔 Напомнить заявителю",
        callback_data=f"unaccepted_remind_{request_number}"
    ))

    # Кнопка принятия заявки менеджером
    builder.row(InlineKeyboardButton(
        text="✅ Принять за заявителя",
        callback_data=f"unaccepted_accept_{request_number}"
    ))

    # Кнопка назад к списку
    builder.row(InlineKeyboardButton(
        text="🔙 К списку непринятых",
        callback_data="unaccepted_back_to_list"
    ))

    return builder.as_markup()


