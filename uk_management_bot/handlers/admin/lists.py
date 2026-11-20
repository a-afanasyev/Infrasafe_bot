"""Менеджер: панели, списки заявок по статусам, архив, закуп."""
from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_request_list_kb,
    get_completed_requests_submenu,
)
from uk_management_bot.keyboards.base import get_user_contextual_keyboard
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_EXECUTED,
)

import html
import logging
from datetime import datetime, timezone
from typing import Optional
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_with_emoji
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access, legacy_primary_role
from uk_management_bot.filters import RoleFilter

from ._router import router

from .shared import (
    ADMIN_PANEL_TEXTS,
    ADMIN_USER_MANAGEMENT_TEXTS,
    ADMIN_EMPLOYEE_MANAGEMENT_TEXTS,
    ADMIN_NEW_REQUESTS_TEXTS,
    ADMIN_ACTIVE_REQUESTS_TEXTS,
    ADMIN_COMPLETED_REQUESTS_TEXTS,
    ADMIN_AWAITING_REVIEW_TEXTS,
    ADMIN_RETURNED_TEXTS,
    ADMIN_NOT_ACCEPTED_TEXTS,
    ADMIN_BACK_TO_MENU_TEXTS,
    ADMIN_ARCHIVE_TEXTS,
    ADMIN_PURCHASE_TEXTS,
)

logger = logging.getLogger(__name__)


MANAGER_LIST_PAGE_SIZE = 10

# вид списка -> (ключ заголовка, ключ «пусто»); {count} в заголовке = всего заявок
_MANAGER_LISTS = {
    "new": ("admin.handlers.new_requests_title", "admin.handlers.no_new_requests"),
    "active": ("admin.handlers.active_requests_title", "admin.handlers.no_active_requests"),
    "executed": ("admin.handlers.completed_requests_title", "admin.handlers.no_completed_requests"),
    "review": ("admin.handlers.all_completed_requests_title", "admin.handlers.no_completed_requests"),
    "returned": ("admin.handlers.returned_requests_title", "admin.handlers.no_returned_requests"),
    "unaccepted": ("admin.handlers.unaccepted_requests_title", "admin.handlers.no_unaccepted_requests"),
    "archive": ("admin.handlers.archive_requests_title", "admin.handlers.archive_empty"),
}
_STATUS_TO_LIST = {
    REQUEST_STATUS_NEW: "new",
    REQUEST_STATUS_EXECUTED: "executed",
    REQUEST_STATUS_IN_PROGRESS: "active",
    REQUEST_STATUS_PURCHASE: "active",
    REQUEST_STATUS_CLARIFICATION: "active",
}


def _waiting_suffix(since: Optional[datetime], lang: str) -> str:
    """«⏳ 2д 3ч» — сколько заявка ждёт приёмки заявителем."""
    if since is None:
        return "⏳ " + get_text("unaccepted.handlers.unknown_short", language=lang)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    waiting = datetime.now(timezone.utc) - since
    days, hours, minutes = waiting.days, waiting.seconds // 3600, (waiting.seconds % 3600) // 60
    d_s, h_s, m_s = (get_text(f"unaccepted.handlers.{unit}_short", language=lang)
                     for unit in ("days", "hours", "minutes"))
    if days > 0:
        return f"⏳ {days}{d_s} {hours}{h_s}"
    if hours > 0:
        return f"⏳ {hours}{h_s} {minutes}{m_s}"
    return f"⏳ {minutes}{m_s}"


def _list_suffix(r, kind: str, lang: str) -> str:
    if kind == "unaccepted":
        return _waiting_suffix(r.completed_at or r.updated_at, lang)
    if kind == "returned" and r.returned_at:
        return r.returned_at.strftime("%d.%m %H:%M")
    if kind in ("review", "executed") and r.is_returned:
        return "🔄 " + get_text("admin.handlers.returned_label", language=lang)
    return ""


def build_manager_list(svc: AdminHandlerService, kind: str, page: int, lang: str) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Текст и клавиатура страницы списка ``kind``; клавиатура None — список пуст.

    Страница за пределами списка прижимается к последней: список мог
    сократиться, пока менеджер держал сообщение открытым.
    """
    title_key, empty_key = _MANAGER_LISTS[kind]
    total = svc.count_manager_list(kind)
    if not total:
        return get_text(empty_key, language=lang), None
    total_pages = (total + MANAGER_LIST_PAGE_SIZE - 1) // MANAGER_LIST_PAGE_SIZE
    page = min(max(page, 1), total_pages)
    requests = svc.page_manager_list(
        kind, (page - 1) * MANAGER_LIST_PAGE_SIZE, MANAGER_LIST_PAGE_SIZE)
    items = [{
        "request_number": r.request_number,
        "category": get_category_display(resolve_category_key(r.category), language=lang),
        "address": r.address,
        "status": r.status,
        "suffix": _list_suffix(r, kind, lang),
    } for r in requests]
    title = get_text(title_key, language=lang).format(count=total)
    return title, get_manager_request_list_kb(items, page, total_pages, language=lang, kind=kind)


async def edit_quiet(callback: CallbackQuery, text: str, markup=None) -> None:
    """`edit_text`, для которого «сообщение не изменено» — не ошибка.

    Так бывает, когда список сократился и страница прижалась к той же, что
    уже на экране: менеджеру незачем видеть «Произошла ошибка».
    """
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def _send_manager_list(message: Message, db: Session, kind: str, lang: str, empty_markup) -> None:
    """Первая страница списка новым сообщением (вход с reply-кнопки меню)."""
    text, markup = build_manager_list(AdminHandlerService(db), kind, 1, lang)
    await message.answer(text, reply_markup=markup or empty_markup)


async def _render_manager_request_list(callback: CallbackQuery, db: Session, request_number, language: str = "ru"):
    """BUG-BOT-035: render-only — перерисовать список заявок менеджера в текущем
    сообщении по `request_number` (берётся аргументом, без парсинга callback.data).

    НЕ проверяет права и НЕ вызывает callback.answer() ни на одном пути — это
    ответственность caller'а. Может бросить исключение; caller оборачивает в
    try/except. Это позволяет звать рендер из cancel/complete/delete, чьи
    callback.data не имеют префикса `mreq_back_`.
    """
    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    # Заявки нет или статус вне списков — показываем активные.
    kind = _STATUS_TO_LIST.get(request.status, "active") if request else "active"
    text, markup = build_manager_list(svc, kind, 1, language)
    await edit_quiet(callback, text, markup)


@router.callback_query(F.data.startswith("mreq_back_"))
async def handle_manager_back_to_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Возврат из деталей заявки к списку для менеджеров (кнопка `mreq_back_<NNN>`).

    Тонкая обёртка: проверка прав + парсинг callback.data → render-only helper.
    """
    try:
        lang = language
        logger.info(f"Возврат к списку заявок менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return

        request_number = callback.data.split("mreq_back_")[1]
        await _render_manager_request_list(callback, db, request_number, lang)

        logger.info(f"Возврат к списку заявок выполнен для менеджера {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка возврата к списку заявок: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.message(F.text.in_(ADMIN_PANEL_TEXTS))
async def open_admin_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None, language: str = "ru"):
    """Открыть админ панель"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer(get_text("admin.handlers.manager_panel", language=lang), reply_markup=get_manager_main_keyboard(language=lang))


@router.message(F.text.in_(ADMIN_USER_MANAGEMENT_TEXTS))  
async def open_user_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Открыть панель управления пользователями"""
    lang = language
    
    # ОТЛАДКА
    logger.debug(f"User management panel opened: user_id={message.from_user.id}, roles={roles}, user_status={user.status if user else None}")
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Импортируем здесь, чтобы избежать циклических импортов
    try:
        from uk_management_bot.handlers.user_management import open_user_management
        await open_user_management(message, db, roles, active_role, user, language=lang)
    except Exception as e:
        logger.error(f"Ошибка в open_user_management: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )


@router.message(F.text.in_(ADMIN_EMPLOYEE_MANAGEMENT_TEXTS))
async def open_employee_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Открыть панель управления сотрудниками"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    try:
        # Получаем статистику сотрудников
        from uk_management_bot.services.user_management_service import UserManagementService
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_employee_stats()
        
        # Показываем главное меню управления сотрудниками
        from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
        
        await message.answer(
            get_text("admin.handlers.employee_management_panel", language=lang),
            reply_markup=get_employee_management_main_keyboard(stats, lang)
        )

    except Exception as e:
        logger.error(f"Ошибка открытия панели управления сотрудниками: {e}")
        await message.answer(get_text("admin.handlers.error_opening_employee_panel", language=lang))


@router.message(F.text.in_(ADMIN_NEW_REQUESTS_TEXTS))
async def list_new_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать новые заявки"""
    lang = language
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    await _send_manager_list(message, db, "new", lang, get_manager_main_keyboard(language=lang))


@router.message(F.text.in_(ADMIN_ACTIVE_REQUESTS_TEXTS))
async def list_active_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать активные заявки"""
    lang = language
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    await _send_manager_list(message, db, "active", lang, get_manager_main_keyboard(language=lang))


@router.message(F.text.in_(ADMIN_COMPLETED_REQUESTS_TEXTS))
async def show_completed_requests_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать подменю для исполненных заявок"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Получаем статистику
    svc = AdminHandlerService(db)
    # "Всего исполненных" = заявки, ожидающие подтверждения менеджером
    total_completed = svc.count_awaiting_manager()

    # Возвращённые = заявка возвращена заявителем на доработку (ждёт разбора менеджером)
    returned_count = svc.count_returned_for_review()

    # Не принятые = подтверждены менеджером, но не приняты заявителем
    unaccepted_count = svc.count_awaiting_applicant()

    stats_text = get_text("admin.handlers.completed_requests_stats", language=lang).format(
        total_completed=total_completed,
        returned_count=returned_count,
        unaccepted_count=unaccepted_count
    )

    await message.answer(stats_text, reply_markup=get_completed_requests_submenu(language=lang), parse_mode="HTML")


@router.message(F.text.in_(ADMIN_AWAITING_REVIEW_TEXTS))
async def list_all_completed_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Заявки, ожидающие подтверждения менеджером."""
    lang = language
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    await _send_manager_list(message, db, "review", lang, get_completed_requests_submenu(language=lang))


@router.message(F.text.in_(ADMIN_RETURNED_TEXTS))
async def list_returned_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Заявки, возвращённые заявителем на доработку."""
    lang = language
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    await _send_manager_list(message, db, "returned", lang, get_completed_requests_submenu(language=lang))


@router.message(F.text.in_(ADMIN_NOT_ACCEPTED_TEXTS))
async def list_unaccepted_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Непринятые заявки: подтверждены менеджером, но не приняты заявителем."""
    lang = language
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    await _send_manager_list(message, db, "unaccepted", lang, get_completed_requests_submenu(language=lang))


@router.message(F.text.in_(ADMIN_BACK_TO_MENU_TEXTS))
async def back_to_main_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться в главное меню"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Импортируем правильную функцию для главного меню
    from uk_management_bot.keyboards.base import get_main_keyboard_for_role

    # Используем универсальную клавиатуру для активной роли пользователя
    await message.answer(
        get_text("menu.main", language=lang),
        reply_markup=get_main_keyboard_for_role(active_role or legacy_primary_role(user), roles or [legacy_primary_role(user)], user.status, language=lang)
    )


# BUG-BOT-019: text "📦 Архив" is shared with the executor main menu. Gate by
# active_role so the admin archive only fires when the user is acting as
# manager/admin. has_admin_access() also runs below but only checks roles list,
# not active_role — RoleFilter is what prevents executor-mode mis-routing.
@router.message(F.text.in_(ADMIN_ARCHIVE_TEXTS), RoleFilter(["manager", "admin"]))
async def list_archive_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать архивные заявки"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Архив — тот же листаемый список, что и остальные: раньше сюда сыпались
    # десять заявок отдельными сообщениями, а одиннадцатая была недоступна.
    # Заявка открывается карточкой; действий у архивной нет — только просмотр.
    await _send_manager_list(message, db, "archive", lang, get_manager_main_keyboard(language=lang))


@router.message(F.text.in_(ADMIN_PURCHASE_TEXTS))
async def list_procurement_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать заявки в статусе закупа"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Получаем заявки в статусе "Закуп"
    requests = AdminHandlerService(db).list_purchase_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_procurement_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return

    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        # A9-P2-2: адрес/категория/примечания — пользовательский текст в
        # HTML-сообщении; экранируем после обрезки (в БД — сырой текст).
        addr = html.escape(r.address[:60]) + ("…" if len(r.address) > 60 else "")
        text = (
            f"{get_status_with_emoji(r.status, language=lang)} #{r.request_number} • {html.escape(r.category or '')}\n"
            + get_text("admin.handlers.archive_address", language=lang).format(address=addr) + "\n"
            + get_text("admin.handlers.archive_created", language=lang).format(created_at=r.created_at.strftime('%d.%m.%Y %H:%M'))
        )
        # Показываем запрошенные материалы и комментарии менеджера
        if r.requested_materials:
            text += "\n" + get_text("admin.handlers.procurement_requested", language=lang).format(materials=html.escape(r.requested_materials))
        if r.manager_materials_comment:
            text += "\n" + get_text("admin.handlers.procurement_manager_comment", language=lang).format(comment=html.escape(r.manager_materials_comment))
        # Для совместимости со старыми записями
        if not r.requested_materials and r.purchase_materials:
            text += "\n" + get_text("admin.handlers.procurement_materials", language=lang).format(materials=html.escape(r.purchase_materials))

        # Создаем инлайн клавиатуру для действий с заявкой
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("admin.handlers.btn_return_to_work", language=lang), callback_data=f"purchase_return_to_work_{r.request_number}")],
            [InlineKeyboardButton(text=get_text("admin.handlers.btn_manager_comment", language=lang), callback_data=f"edit_materials_{r.request_number}")]
        ])

        await message.answer(text, reply_markup=keyboard)

    await message.answer(get_text("admin.handlers.procurement_end", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
    logger.info(f"Показаны заявки в статусе закуп менеджеру {message.from_user.id}")






