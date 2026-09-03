from typing import Optional

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from uk_management_bot.utils.request_helpers import RequestCallbackHelper
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.user_names import display_name
from uk_management_bot.utils.status_display import STATUS_EMOJI


def get_manager_main_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=get_text("admin.keyboards.new_requests", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.active_requests", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.completed_requests", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.purchase", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.archive", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.shifts", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.address_directory", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.user_management", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.employee_management", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.create_invite", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.back", language=language)))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_completed_requests_submenu(language: str = "ru") -> ReplyKeyboardMarkup:
    """Подменю для раздела 'Исполненные заявки'"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=get_text("admin.keyboards.awaiting_review", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.returned", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.not_accepted", language=language)))
    builder.add(KeyboardButton(text=get_text("admin.keyboards.back_to_menu", language=language)))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_manager_requests_inline(page: int, total_pages: int, language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.add(InlineKeyboardButton(text="◀️", callback_data=f"mreq_page_{page-1}"))
    builder.add(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="mreq_page_curr"))
    if page < total_pages:
        builder.add(InlineKeyboardButton(text="▶️", callback_data=f"mreq_page_{page+1}"))
    builder.adjust(3)
    return builder.as_markup()


def _status_icon(status: str) -> str:
    """Return status emoji from the centralised STATUS_EMOJI mapping."""
    return STATUS_EMOJI.get(status, "📋")


def get_manager_request_list_kb(requests: list[dict], page: int, total_pages: int, language: str = "ru") -> InlineKeyboardMarkup:
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


def get_invite_role_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора роли для приглашения"""
    builder = InlineKeyboardBuilder()
    # «Заявитель» убран (BUG-164, решение владельца 2026-08-19): житель
    # регистрируется сам, а такой инвайт лишь сжигал одноразовый токен,
    # не меняя ролей — неотличимо от «токен не сработал».
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.role_executor", language=language), callback_data="invite_role_executor"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.role_manager", language=language), callback_data="invite_role_manager"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.role_inspector", language=language), callback_data="invite_role_inspector"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.cancel", language=language), callback_data="invite_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_invite_specialization_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора специализации для исполнителя"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_plumber", language=language), callback_data="invite_spec_plumber"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_electrician", language=language), callback_data="invite_spec_electrician"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_hvac", language=language), callback_data="invite_spec_hvac"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_cleaning", language=language), callback_data="invite_spec_cleaning"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_security", language=language), callback_data="invite_spec_security"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_maintenance", language=language), callback_data="invite_spec_maintenance"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_landscaping", language=language), callback_data="invite_spec_landscaping"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_repair", language=language), callback_data="invite_spec_repair"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.spec_installation", language=language), callback_data="invite_spec_installation"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.cancel", language=language), callback_data="invite_cancel"))
    builder.adjust(2)
    return builder.as_markup()


def get_invite_expiry_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора срока действия приглашения"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.expiry_1h", language=language), callback_data="invite_expiry_1h"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.expiry_24h", language=language), callback_data="invite_expiry_24h"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.expiry_7d", language=language), callback_data="invite_expiry_7d"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.cancel", language=language), callback_data="invite_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_invite_confirmation_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания приглашения"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.confirm_create_invite", language=language), callback_data="invite_confirm"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.cancel", language=language), callback_data="invite_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_user_approval_keyboard(user_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для одобрения/отклонения пользователя"""
    import logging
    logger = logging.getLogger(__name__)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.approve", language=language), callback_data=f"approve_user_{user_id}"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.reject", language=language), callback_data=f"reject_user_{user_id}"))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.view_profile", language=language), callback_data=f"view_user_{user_id}"))
    builder.adjust(2)

    logger.info(f"🟢 Создана клавиатура одобрения для user_id={user_id}")
    logger.info(f"🟢 Кнопки: approve_user_{user_id}, reject_user_{user_id}, view_user_{user_id}")

    return builder.as_markup()


def get_manager_request_actions_keyboard(request_number: str, has_media: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий с заявкой для менеджеров

    Args:
        request_number: Номер заявки
        has_media: Есть ли прикрепленные медиафайлы к заявке
        language: Язык интерфейса
    """
    builder = InlineKeyboardBuilder()

    # Основные действия с заявкой - сокращенный текст для лучшей читаемости
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.to_work", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("accept_", request_number)))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.decline", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mgr_deny_", request_number)))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.clarify", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("clarify_", request_number)))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.to_purchase", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("purchase_", request_number)))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.complete", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mgr_complete_", request_number)))
    builder.add(InlineKeyboardButton(text=get_text("admin.keyboards.delete", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mgr_delete_", request_number)))

    # Настройка расположения кнопок (2 кнопки в ряд для основных действий)
    builder.adjust(2)

    # Кнопка для просмотра медиафайлов - показывается только если есть медиа
    if has_media:
        builder.row(InlineKeyboardButton(text=get_text("admin.keyboards.media", language=language), callback_data=RequestCallbackHelper.create_callback_data_with_request_number("media_", request_number)))

    return builder.as_markup()


def get_manager_completed_request_actions_keyboard(request_number: str, is_returned: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий с исполненной заявкой для менеджера

    Args:
        request_number: Номер заявки
        is_returned: Возвращена ли заявка заявителем
        language: Язык интерфейса
    """
    builder = InlineKeyboardBuilder()

    if is_returned:
        # Для возвратных заявок - показать другие действия
        builder.row(InlineKeyboardButton(
            text=get_text("admin.keyboards.reconfirm", language=language),
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("reconfirm_completed_", request_number)
        ))
        builder.row(InlineKeyboardButton(
            text=get_text("admin.keyboards.return_to_work", language=language),
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("return_to_work_", request_number)
        ))
    else:
        # Для обычных исполненных заявок
        builder.row(InlineKeyboardButton(
            text=get_text("admin.keyboards.confirm_completion", language=language),
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("confirm_completed_", request_number)
        ))
        builder.row(InlineKeyboardButton(
            text=get_text("admin.keyboards.return_to_work", language=language),
            callback_data=RequestCallbackHelper.create_callback_data_with_request_number("return_to_work_", request_number)
        ))

    return builder.as_markup()


def get_rating_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура с оценками 1-5 звёзд для заявителя

    Args:
        request_number: Номер заявки
        language: Язык интерфейса
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


def get_applicant_completed_request_actions_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий с выполненной заявкой для заявителя

    Args:
        request_number: Номер заявки
        language: Язык интерфейса
    """
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.accept_request", language=language),
        callback_data=f"accept_request_{request_number}"
    ))
    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.return_request", language=language),
        callback_data=f"return_request_{request_number}"
    ))
    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.back_nav", language=language),
        callback_data="back_to_pending_acceptance"
    ))

    return builder.as_markup()


def get_skip_media_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Пропустить' для медиа"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_text("admin.keyboards.skip", language=language), callback_data="skip_return_media"))
    return builder.as_markup()


def get_assignment_type_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора типа назначения исполнителя"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.assign_duty_specialist", language=language),
        callback_data=f"assign_duty_{request_number}"
    ))

    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.assign_specific_executor", language=language),
        callback_data=f"assign_specific_{request_number}"
    ))

    return builder.as_markup()


def get_reassign_button_row(
    request_number: str,
    *,
    assignment_type: Optional[str],
    status: Optional[str],
    has_executor: bool = False,
    roles: Optional[list] = None,
    language: str = "ru",
) -> list:
    """Строка «Переназначить» для карточки менеджера — или пустой список.

    Условия показа держатся вместе, чтобы кнопка не появлялась там, где канон
    её всё равно не пустит:

    * статус — из `MANAGER_ASSIGN.from_statuses` (сегодня «Новая»/«В работе»);
    * назначение должно БЫТЬ — но «есть назначение» это НЕ то же самое, что
      «есть активная строка RequestAssignment»: у заявок, назначенных до
      миграции 011, строки нет, а `request.executor_id` заполнен, и канон
      переназначение таких пускает. На проде это не редкость — на profk на
      момент раскатки ВСЕ заявки «В работе» были именно такими, то есть завязка
      только на строку прятала кнопку почти везде;
    * роль — именно `manager`: `has_admin_access` пропускает и чистого `admin`,
      а канон требует менеджера, и такая кнопка вела бы админа в отказ.

    Подпись зависит от того, есть ли КОНКРЕТНЫЙ исполнитель: при чисто
    групповом назначении снимать некого — это «назначить», а не «переназначить».
    """
    from uk_management_bot.utils.workflow_predicates import reassignable_statuses

    # Источник — САМ канон (`MANAGER_ASSIGN.from_statuses`), а не свой список:
    # второе определение того же правила разъехалось бы при правке specs.py
    # молча — кнопка пряталась бы там, где команда уже проходит.
    if status not in reassignable_statuses():
        return []
    individual = has_executor or assignment_type == "individual"
    if not individual and assignment_type != "group":
        return []
    if "manager" not in set(roles or []):
        # Здесь намеренно только `roles`: карточка рисуется хендлером, который
        # роли из middleware получает всегда. Скрытая кнопка — косметика, а
        # настоящий гейт стоит в хендлерах (has_manager_role с fallback).
        return []

    key = ("admin.keyboards.reassign_request" if individual
           else "admin.keyboards.assign_executor_to_request")
    return [InlineKeyboardButton(
        text=get_text(key, language=language),
        callback_data=f"req_reassign_menu_{request_number}",
    )]


def get_executors_by_category_keyboard(
    request_number: str,
    category: str,
    executors: list,
    language: str = "ru",
    callback_prefix: str = "assign_executor_",
    back_callback_data: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Клавиатура со списком исполнителей для данной категории.

    `callback_prefix` и `back_callback_data` параметризованы, потому что этот
    же список нужен переназначению, а зашитые значения увели бы его в чужой
    флоу: кнопки вели бы на первичное назначение, а «Назад» — на выбор типа
    назначения вместо меню переназначения. Дефолты равны прежним константам,
    поэтому существующие вызовы не меняются.
    """
    builder = InlineKeyboardBuilder()

    if not executors:
        builder.row(InlineKeyboardButton(
            text=get_text("admin.keyboards.no_available_executors", language=language),
            callback_data="no_executors"
        ))
    else:
        for executor in executors:
            # Формируем текст кнопки с информацией об исполнителе
            name = display_name(executor)

            # Добавляем статус смены если есть
            status_icon = "🟢" if hasattr(executor, 'on_shift') and executor.on_shift else "⚪"

            button_text = f"{status_icon} {name}"

            builder.row(InlineKeyboardButton(
                text=button_text,
                callback_data=f"{callback_prefix}{request_number}_{executor.id}"
            ))

    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.back_nav", language=language),
        callback_data=back_callback_data or f"back_to_assignment_type_{request_number}"
    ))

    return builder.as_markup()


def get_unaccepted_request_actions_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий для непринятой заявки (для менеджера)

    Args:
        request_number: Номер заявки
        language: Язык интерфейса

    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    builder = InlineKeyboardBuilder()

    # Кнопка повторного уведомления заявителя
    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.remind_applicant", language=language),
        callback_data=f"unaccepted_remind_{request_number}"
    ))

    # Кнопка принятия заявки менеджером
    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.accept_for_applicant", language=language),
        callback_data=f"unaccepted_accept_{request_number}"
    ))

    # Кнопка назад к списку
    builder.row(InlineKeyboardButton(
        text=get_text("admin.keyboards.back_to_unaccepted_list", language=language),
        callback_data="unaccepted_back_to_list"
    ))

    return builder.as_markup()


def get_change_category_button_row(
    request_number: str,
    *,
    status: str,
    roles: Optional[list] = None,
    language: str = "ru",
) -> list:
    """Строка «Категория» для карточки менеджера — или пустой список.

    Условия совпадают с каноном MANAGER_CHANGE_CATEGORY: любой нетерминальный
    статус и роль именно `manager` (`has_admin_access` пропускает чистого
    `admin`, а канон его отправил бы в отказ).
    """
    from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES

    if status in TERMINAL_STATUSES:
        return []
    if "manager" not in set(roles or []):
        return []
    return [InlineKeyboardButton(
        text=get_text("admin.keyboards.change_category", language=language),
        callback_data=f"req_category_menu_{request_number}",
    )]


def get_category_picker_keyboard(
    request_number: str,
    current_key: Optional[str],
    language: str = "ru",
) -> InlineKeyboardMarkup:
    """Picker категорий по SELECTABLE (служебная `engineering` не предлагается),
    2 в ряд, текущая помечена «• », внизу — назад к карточке."""
    from uk_management_bot.keyboards.requests import (
        SELECTABLE_CATEGORY_KEYS,
        get_category_display,
    )

    rows: list = []
    row: list = []
    for key in SELECTABLE_CATEGORY_KEYS:
        label = get_category_display(key, language)
        if key == current_key:
            label = f"• {label}"
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"req_category_set_{request_number}_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(
        text=get_text("admin.keyboards.back_to_request", language=language),
        callback_data=f"mview_{request_number}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
