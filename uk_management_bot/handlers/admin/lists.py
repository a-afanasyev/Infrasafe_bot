"""Менеджер: панели, списки заявок по статусам, архив, закуп."""
from aiogram import F
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
    REQUEST_STATUS_CANCELLED,
)

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_with_emoji
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access, legacy_primary_role, parse_roles_safe
from uk_management_bot.filters import RoleFilter
from datetime import datetime, timezone

from ._router import router

from .shared import (
    ADMIN_PANEL_TEXTS,
    TEST_MIDDLEWARE_TEXTS,
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


async def _render_manager_request_list(callback: CallbackQuery, db: Session, request_number, language: str = "ru"):
    """BUG-BOT-035: render-only — перерисовать список заявок менеджера в текущем
    сообщении по `request_number` (берётся аргументом, без парсинга callback.data).

    НЕ проверяет права и НЕ вызывает callback.answer() ни на одном пути — это
    ответственность caller'а. Может бросить исключение; caller оборачивает в
    try/except. Это позволяет звать рендер из cancel/complete/delete, чьи
    callback.data не имеют префикса `mreq_back_`.
    """
    lang = language
    from uk_management_bot.keyboards.admin import get_manager_request_list_kb

    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)

    if request:
        if request.status == REQUEST_STATUS_NEW:
            requests = svc.list_new_requests(limit=10)
            if not requests:
                await callback.message.edit_text(get_text("admin.handlers.no_new_requests", language=lang))
                return
            items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
            keyboard = get_manager_request_list_kb(items, 1, 1)
            await callback.message.edit_text(get_text("admin.handlers.new_requests_title", language=lang), reply_markup=keyboard)
            return

        elif request.status == REQUEST_STATUS_EXECUTED:
            requests = svc.list_executed_requests(limit=10)
            if not requests:
                await callback.message.edit_text(get_text("admin.handlers.no_completed_requests", language=lang))
                return
            items = []
            for r in requests:
                item = {"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status}
                if r.is_returned:
                    item["suffix"] = " 🔄"
                items.append(item)
            keyboard = get_manager_request_list_kb(items, 1, 1)
            await callback.message.edit_text(get_text("admin.handlers.completed_requests_title", language=lang), reply_markup=keyboard)
            return

        elif request.status in [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]:
            requests = svc.list_active_requests(limit=10)
            if not requests:
                await callback.message.edit_text(get_text("admin.handlers.no_active_requests", language=lang))
                return
            items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
            keyboard = get_manager_request_list_kb(items, 1, 1)
            await callback.message.edit_text(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=keyboard)
            return

    # Fallback: показываем активные заявки по умолчанию
    requests = svc.list_active_requests(limit=10)

    if not requests:
        await callback.message.edit_text(get_text("admin.handlers.no_active_requests", language=lang))
        return

    items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
    keyboard = get_manager_request_list_kb(items, 1, 1)
    await callback.message.edit_text(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=keyboard)


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


@router.message(F.text.in_(TEST_MIDDLEWARE_TEXTS))
async def test_middleware(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None, language: str = "ru"):
    """Тестовый обработчик для проверки middleware"""
    
    # Логирование параметров middleware для отладки
    logger.debug(f"Admin panel access check: roles={roles}, active_role={active_role}, user_id={message.from_user.id}")
    
    # Проверяем доступ к админ панели
    has_access = False
    if roles:
        has_access = any(role in ['admin', 'manager'] for role in roles)
    elif user and user.roles:
        # COD-01: канонический парсер ролей (JSON+CSV)
        user_roles = parse_roles_safe(user.roles)
        has_access = any(role in ['admin', 'manager'] for role in user_roles)
    
    print(f"🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
    
    lang = language
    await message.answer(get_text("admin.handlers.test_middleware_result", language=lang).format(
        roles=roles, active_role=active_role,
        user_status=get_text("admin.handlers.yes", language=lang) if user else get_text("admin.handlers.no", language=lang),
        has_access=get_text("admin.handlers.yes", language=lang) if has_access else get_text("admin.handlers.no", language=lang)
    ))

@router.message(F.text.in_(ADMIN_PANEL_TEXTS))
async def open_admin_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None, language: str = "ru"):
    """Открыть админ панель"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
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
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Импортируем здесь, чтобы избежать циклических импортов
    try:
        from uk_management_bot.handlers.user_management import open_user_management
        await open_user_management(message, db, roles, active_role, user)
    except ImportError as e:
        logger.error(f"Ошибка импорта open_user_management: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )
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
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
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
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Новые заявки: только "Новая" (🆕)
    requests = AdminHandlerService(db).list_new_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_new_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return

    items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
    await message.answer(get_text("admin.handlers.new_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text.in_(ADMIN_ACTIVE_REQUESTS_TEXTS))
async def list_active_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать активные заявки"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    requests = AdminHandlerService(db).list_active_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_active_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return

    items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
    await message.answer(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text.in_(ADMIN_COMPLETED_REQUESTS_TEXTS))
async def show_completed_requests_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать подменю для исполненных заявок"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
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
    """Показать заявки, ожидающие проверки менеджером"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Все исполненные заявки: статус "Выполнена" и НЕ подтверждены менеджером
    # (ожидают проверки и подтверждения менеджером)
    requests = AdminHandlerService(db).list_awaiting_manager(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_completed_requests", language=lang), reply_markup=get_completed_requests_submenu(language=lang))
        return

    # Добавляем пометку "возвратная" для возвратных заявок
    items = []
    for r in requests:
        item = {
            "request_number": r.request_number,
            "category": get_category_display(resolve_category_key(r.category), language=lang),
            "address": r.address,
            "status": "🔄 " + get_text("admin.handlers.returned_label", language=lang) if r.is_returned else r.status
        }
        items.append(item)

    await message.answer(get_text("admin.handlers.all_completed_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text.in_(ADMIN_RETURNED_TEXTS))
async def list_returned_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать только возвращённые заявки"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Только возвращённые заявки
    # Статус "Исполнено" - когда заявка возвращена заявителем на доработку
    requests = AdminHandlerService(db).list_returned_for_review(limit=10)

    if not requests:
        await message.answer(
            get_text("admin.handlers.no_returned_requests", language=lang),
            reply_markup=get_completed_requests_submenu(language=lang)
        )
        return

    items = []
    for r in requests:
        # Форматируем информацию о возврате
        return_info = ""
        if r.returned_at:
            return_info = f" • {r.returned_at.strftime('%d.%m %H:%M')}"

        item = {
            "request_number": r.request_number,
            "category": get_category_display(resolve_category_key(r.category), language=lang),
            "address": r.address,
            "status": get_text("admin.handlers.returned_status_label", language=lang) + return_info
        }
        items.append(item)

    await message.answer(
        get_text("admin.handlers.returned_requests_title", language=lang).format(count=len(requests)),
        reply_markup=get_manager_request_list_kb(items, 1, 1),
        parse_mode="HTML"
    )


@router.message(F.text.in_(ADMIN_NOT_ACCEPTED_TEXTS))
async def list_unaccepted_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать непринятые заявки (выполненные, но не принятые заявителем)"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Непринятые заявки: подтверждены менеджером (manager_confirmed = True), но не приняты заявителем (статус != "Принято")
    requests = AdminHandlerService(db).list_awaiting_applicant(limit=20)

    if not requests:
        await message.answer(
            get_text("admin.handlers.no_unaccepted_requests", language=lang),
            reply_markup=get_completed_requests_submenu(language=lang),
            parse_mode="HTML"
        )
        return

    # Форматируем список заявок с указанием времени ожидания
    items = []
    now = datetime.now(timezone.utc)

    for r in requests:
        # Вычисляем время ожидания с момента завершения
        completed_at = r.completed_at if r.completed_at else r.updated_at
        if completed_at:
            # Обеспечиваем что completed_at timezone-aware
            if completed_at.tzinfo is None:
                from datetime import timezone as dt_tz
                completed_at = completed_at.replace(tzinfo=dt_tz.utc)

            waiting_time = now - completed_at
            days = waiting_time.days
            hours = waiting_time.seconds // 3600
            minutes = (waiting_time.seconds % 3600) // 60

            if days > 0:
                time_str = f"{days}д {hours}ч"
            elif hours > 0:
                time_str = f"{hours}ч {minutes}м"
            else:
                time_str = f"{minutes}м"
        else:
            time_str = get_text("admin.handlers.time_unknown", language=lang)

        item = {
            "request_number": r.request_number,
            "category": get_category_display(resolve_category_key(r.category), language=lang),
            "address": r.address or get_text("admin.handlers.address_not_specified", language=lang),
            "status": f"⏳ {time_str}"
        }
        items.append(item)

    from uk_management_bot.keyboards.admin import get_manager_request_list_kb
    await message.answer(
        get_text("admin.handlers.unaccepted_requests_title", language=lang).format(count=len(requests)),
        reply_markup=get_manager_request_list_kb(items, 1, 1),
        parse_mode="HTML"
    )


@router.message(F.text.in_(ADMIN_BACK_TO_MENU_TEXTS))
async def back_to_main_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться в главное меню"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
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
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Архив: только завершенные статусы (Выполнена, Исполнено, Принято, Отменена)
    requests = AdminHandlerService(db).list_archive_requests(limit=10)
    if not requests:
        await message.answer(get_text("admin.handlers.archive_empty", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return
    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"{get_status_with_emoji(r.status, language=lang)} #{r.request_number} • {r.category}\n"
            + get_text("admin.handlers.archive_address", language=lang).format(address=addr) + "\n"
            + get_text("admin.handlers.archive_created", language=lang).format(created_at=r.created_at.strftime('%d.%m.%Y %H:%M'))
        )
        if r.notes and r.notes.strip():
            if r.status == REQUEST_STATUS_CANCELLED:
                text += "\n" + get_text("admin.handlers.archive_cancel_reason", language=lang).format(reason=r.notes.strip())
            else:
                text += "\n" + get_text("admin.handlers.archive_notes", language=lang).format(notes=r.notes.strip())
        await message.answer(text)
    await message.answer(get_text("admin.handlers.archive_end", language=lang), reply_markup=get_manager_main_keyboard(language=lang))

@router.message(F.text.in_(ADMIN_PURCHASE_TEXTS))
async def list_procurement_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать заявки в статусе закупа"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Получаем заявки в статусе "Закуп"
    requests = AdminHandlerService(db).list_purchase_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_procurement_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return

    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"{get_status_with_emoji(r.status, language=lang)} #{r.request_number} • {r.category}\n"
            + get_text("admin.handlers.archive_address", language=lang).format(address=addr) + "\n"
            + get_text("admin.handlers.archive_created", language=lang).format(created_at=r.created_at.strftime('%d.%m.%Y %H:%M'))
        )
        # Показываем запрошенные материалы и комментарии менеджера
        if r.requested_materials:
            text += "\n" + get_text("admin.handlers.procurement_requested", language=lang).format(materials=r.requested_materials)
        if r.manager_materials_comment:
            text += "\n" + get_text("admin.handlers.procurement_manager_comment", language=lang).format(comment=r.manager_materials_comment)
        # Для совместимости со старыми записями
        if not r.requested_materials and r.purchase_materials:
            text += "\n" + get_text("admin.handlers.procurement_materials", language=lang).format(materials=r.purchase_materials)

        # Создаем инлайн клавиатуру для действий с заявкой
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("admin.handlers.btn_return_to_work", language=lang), callback_data=f"purchase_return_to_work_{r.request_number}")],
            [InlineKeyboardButton(text=get_text("admin.handlers.btn_manager_comment", language=lang), callback_data=f"edit_materials_{r.request_number}")]
        ])

        await message.answer(text, reply_markup=keyboard)

    await message.answer(get_text("admin.handlers.procurement_end", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
    logger.info(f"Показаны заявки в статусе закуп менеджеру {message.from_user.id}")






