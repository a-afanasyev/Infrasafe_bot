"""Просмотр/пагинация/редактирование/отмена/одобрение заявки; query-хелперы."""

import json

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
from uk_management_bot.services.request_handler_service import RequestHandlerService

from uk_management_bot.keyboards.requests import (
    get_categories_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard
import logging
from uk_management_bot.services.request_service import RequestService

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.status_display import get_status_display as _sd_get_status_display, STATUS_EMOJI
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix

from ._router import router

from .shared import (
    _db_scope,
    RequestStates,
    _VIEW_REQUEST_NUMBER_RE,
    _CANCEL_REQUEST_NUMBER_RE,
    _EDIT_REQUEST_NUMBER_RE,
    _APPROVE_REQUEST_NUMBER_RE,
)

logger = logging.getLogger(__name__)


def _get_executor_requests_query(db_session: Session, user: User):
    """Заявки исполнителя — ТОЛЬКО его персональные (individual / взятые).

    Тонкая обёртка над ``RequestHandlerService.get_executor_requests_query``
    (ARCH-01: ORM в сервисе). Сохранена как публичная точка входа для
    tests/services/test_group_pool_query.py (вызывает ``.all()`` на результате).
    """
    return RequestHandlerService(db_session).get_executor_requests_query(user)


def _get_group_pool_query(db_session: Session, user: User):
    """FEAT-группы: пул «свободных» group-заявок для исполнителя.

    Тонкая обёртка над ``RequestHandlerService.get_group_pool_query`` (ARCH-01:
    ORM в сервисе). Сохранена как публичная точка входа для
    tests/services/test_group_pool_query.py.
    """
    return RequestHandlerService(db_session).get_group_pool_query(user)


@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Обработка пагинации списков заявок"""
    try:
        logger.info(f"Обработка пагинации для пользователя {callback.from_user.id}")

        # Парсим данные пагинации
        current_page = int(callback.data.replace("page_", ""))

        # Читаем активный фильтр из FSM
        data = await state.get_data()
        active_status = data.get("my_requests_status")

        # Получаем список заявок пользователя с учетом фильтра
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            # Получаем пользователя из базы данных по telegram_id
            user = service.get_user_by_telegram_id(callback.from_user.id)

            if not user:
                await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
                return

            # Определяем активную роль пользователя
            # WR-10: единый канон-парсер ролей вместо хрупкого ручного
            # strip('[]').replace('"','').split(', ') по JSON-строке.
            user_roles = parse_roles_safe(user.roles)
            active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

            # Получаем заявки в зависимости от роли + status-фильтр (ORM в сервисе)
            user_requests = service.list_pagination_requests(user, active_role, active_status)

        # Вычисляем общее количество страниц
        total_requests = len(user_requests)
        requests_per_page = 5
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)

        if current_page < 1 or current_page > total_pages:
            await callback.answer(get_text("requests.page_not_found", language=lang), show_alert=True)
            return

        # Получаем заявки для текущей страницы
        start_idx = (current_page - 1) * requests_per_page
        end_idx = start_idx + requests_per_page
        page_requests = user_requests[start_idx:end_idx]

        # BUG-BOT-008: Унифицированный заголовок (см. format_requests_list_header).
        # Использует единый шаблон для Page1/Page2/Активные/Архив.
        from uk_management_bot.utils.request_helpers import format_requests_list_header
        message_text = format_requests_list_header(
            total_requests=total_requests,
            current_page=current_page,
            total_pages=total_pages,
            status_filter=active_status or "all",
            role=active_role,
            language=lang,
        )
        # TASK 17 Этап A: Используем resolve_category_key и get_category_display для нормализации категорий
        # TASK 17 Этап C: Локализуем статусы через status_display.py
        from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
        for i, request in enumerate(page_requests, 1):
            category_key = resolve_category_key(request.category)
            category_display = get_category_display(category_key, language=lang)
            status_display = _sd_get_status_display(request.status, language=lang)
            icon = STATUS_EMOJI.get(request.status, "📋")
            message_text += f"{i}. {icon} #{request.request_number} - {category_display} - {status_display}\n"
            # TASK 17 Этап C: Локализованные метки
            address_label = get_text("requests.address_label", language=lang) or "Адрес"
            created_label = get_text("requests.created_label", language=lang) or "Создана"
            from uk_management_bot.utils.address_helpers import localize_address
            message_text += f"   {address_label} {localize_address(request.address, lang)}\n"
            message_text += f"   {created_label} {request.created_at.strftime('%d.%m.%Y')}\n"
            if request.status == "Отменена" and request.notes:
                # TASK 17 Этап C: Локализованная метка
                reason_label = get_text("requests.cancellation_reason_label", language=lang) or "Причина отказа"
                message_text += f"   {reason_label} {request.notes}\n"
            elif request.status == "Уточнение" and request.notes:
                # Показываем последние сообщения из диалога уточнения
                # TASK 17 Этап C: Локализованная метка
                clarification_label = get_text("requests.clarification_label", language=lang) or "Уточнение"
                notes_lines = request.notes.strip().split('\n')
                last_messages = [line for line in notes_lines[-3:] if line.strip()]  # Последние 3 сообщения
                if last_messages:
                    preview = '\n'.join(last_messages)
                    if len(preview) > 100:
                        preview = preview[:97] + '...'
                    message_text += f"   {clarification_label}: {preview}\n"
            message_text += "\n"
        
        # Создаем комбинированную клавиатуру: фильтр + кнопки ответа (по каждой) + пагинация
        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        from uk_management_bot.keyboards.requests import get_status_filter_inline_keyboard
        filter_kb = get_status_filter_inline_keyboard(active_status if active_status != "all" else None, language=lang)
        rows = list(filter_kb.inline_keyboard)
        for i, r in enumerate(page_requests, 1):
            if r.status == "Уточнение":
                # TASK 17 Этап C: Локализованная кнопка ответа
                reply_text = get_text("buttons.reply", language=lang) or "💬 Ответить"
                rows.append([InlineKeyboardButton(text=f"{reply_text} по #{r.request_number}", callback_data=f"replyclarify_{r.request_number}")])
        pagination_kb = get_pagination_keyboard(current_page, total_pages, request_number=None, show_reply_clarify=False)
        rows += pagination_kb.inline_keyboard
        combined = InlineKeyboardMarkup(inline_keyboard=rows)

        # Сохраняем текущую страницу в FSM
        await state.update_data(my_requests_page=current_page)

        try:
            await callback.message.edit_text(message_text, reply_markup=combined)
        except TelegramBadRequest:
            pass
        
        logger.info(f"Показана страница {current_page} для пользователя {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки пагинации: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)

@router.callback_query(
    # BUG-BOT-033 fix: replace fragile prefix-match + maintained exclusion list
    # with strict regex matching request_number format `view_<YYMMDD-NNN>` or
    # `view_request_<YYMMDD-NNN>`. Any other view_* callback (view_current_shifts,
    # view_apartment:N, view_week_schedule, etc.) is no longer hijacked here and
    # reaches its own handler in a later router.
    F.data.regexp(_VIEW_REQUEST_NUMBER_RE)
)
async def handle_view_request(callback: CallbackQuery, state: FSMContext):
    """Обработка просмотра деталей заявки"""
    try:
        logger.info(f"Обработка просмотра заявки для пользователя {callback.from_user.id}")

        # Извлекаем номер заявки из callback_data (view_ или view_request_)
        request_number = callback.data.replace("view_request_", "").replace("view_", "")

        # Получаем заявку из базы данных
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            request = service.get_request_by_number(request_number)

            if not request:
                await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
                return

            # Получаем пользователя и проверяем права доступа
            user = service.get_user_by_telegram_id(callback.from_user.id)

            if not user:
                await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
                return

            # Определяем роль пользователя (COD-01: канонический парсер, JSON+CSV)
            user_roles = parse_roles_safe(user.roles)

            active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

            # Проверяем права доступа в зависимости от роли
            has_access = False

            if active_role == "executor":
                # BUG-BOT-004: прямое назначение через Request.executor_id (FK)
                # имеет приоритет — если исполнитель назначен напрямую, он видит заявку
                # независимо от наличия записей в RequestAssignment.
                if request.executor_id == user.id:
                    has_access = True

                # Для исполнителей: проверяем назначение
                assignment = service.get_active_assignment(request.request_number)

                if not has_access and assignment:
                    # Индивидуальное назначение
                    if assignment.executor_id == user.id:
                        has_access = True
                    # Групповое назначение по специализациям
                    elif assignment.assignment_type == "group":
                        # Получаем ВСЕ специализации исполнителя
                        executor_specializations = []
                        if user.specialization:
                            try:
                                if isinstance(user.specialization, str) and user.specialization.startswith('['):
                                    executor_specializations = json.loads(user.specialization)
                                else:
                                    executor_specializations = [user.specialization]
                            except (json.JSONDecodeError, TypeError):
                                executor_specializations = [user.specialization] if user.specialization else []

                        # Проверяем, есть ли совпадение с хотя бы одной специализацией
                        if assignment.group_specialization in executor_specializations:
                            has_access = True
            else:
                # Для заявителей и других ролей: проверяем владение заявкой или квартиры
                if request.user_id == user.id:
                    has_access = True
                elif request.apartment_id:
                    if service.is_apartment_resident(user.id, request.apartment_id):
                        has_access = True

            if not has_access:
                await callback.answer(get_text("requests.no_access_to_request", language=lang), show_alert=True)
                return

            # TASK 17 Issue #4: Use localized helper function for request details
            # Replaces 18 lines of hard-coded Russian text with reusable helper
            from uk_management_bot.utils.request_helpers import format_request_details

            message_text = format_request_details(
                request=request,
                language=lang,
                show_executor=True,
                active_role=active_role,
                db_session=db_session
            )

        # Check media files for keyboard logic
        has_media = bool(request.media_files)
        media_count = 0
        if has_media:
            try:
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
                media_count = len(media_files) if media_files else 0
                if media_count == 0:
                    has_media = False
            except (json.JSONDecodeError, TypeError):
                has_media = False

        # Создаем клавиатуру в зависимости от роли
        rows = []

        if active_role == "executor":
            # Для исполнителей: только действия по работе с заявкой
            # TASK 17 Этап C: Локализованные кнопки
            if request.status == "В работе" and request.executor_id is None:
                # FEAT-группы: непривязанная group-заявка → «Взять» (а не
                # Выполнена/Закуп — работать может только взявший; авторизацию
                # взятия проверяет EXECUTOR_CLAIM в claim-callback).
                # WR-04: показываем «Взять» только дежурным (on-shift) — иначе
                # не-дежурный жал бы кнопку и получал NotAuthorized («уже взяли»),
                # хотя реальная причина — вне смены. Вне смены кнопок действий нет.
                from uk_management_bot.utils.shifts import is_on_shift_now_sync
                if is_on_shift_now_sync(db_session, user.id):
                    claim_text = get_text("requests.executor_claim_button", language=lang) or "🙋 Взять в работу"
                    rows.append([InlineKeyboardButton(text=claim_text, callback_data=f"claim_request_{request.request_number}")])
            elif request.status == "В работе":
                complete_text = get_text("buttons.complete", language=lang) or "✅ Выполнена"
                purchase_text = get_text("buttons.purchase", language=lang) or "💰 Нужен закуп"
                rows.append([InlineKeyboardButton(text=complete_text, callback_data=f"executor_complete_{request.request_number}")])
                rows.append([InlineKeyboardButton(text=purchase_text, callback_data=f"executor_purchase_{request.request_number}")])
            elif request.status == "Закуп":
                back_to_work_text = get_text("buttons.back_to_work", language=lang) or "🔄 Вернуть в работу"
                rows.append([InlineKeyboardButton(text=back_to_work_text, callback_data=f"executor_work_{request.request_number}")])
            elif request.status == "Уточнение":
                back_to_work_text = get_text("buttons.back_to_work", language=lang) or "🔄 Вернуть в работу"
                rows.append([InlineKeyboardButton(text=back_to_work_text, callback_data=f"executor_work_{request.request_number}")])
            elif request.status in ["Выполнена", "Исполнено", "Принято"]:
                # Заявка завершена - только просмотр
                pass

            # Кнопка просмотра медиа (если есть)
            # TASK 17 Этап C: Локализованная кнопка
            if has_media:
                view_media_text = get_text("buttons.view_media", language=lang) or "📎 Просмотр медиа"
                rows.append([InlineKeyboardButton(text=view_media_text, callback_data=f"executor_view_media_{request.request_number}")])
        elif active_role in ["admin", "manager"]:
            # Для менеджеров/админов: полная клавиатура управления
            # TASK 17 Этап C: Передаём язык для локализации кнопок
            from uk_management_bot.keyboards.requests import get_request_actions_keyboard
            actions_kb = get_request_actions_keyboard(request.request_number, language=lang)
            rows = list(actions_kb.inline_keyboard)
        else:
            # Для заявителей: ограниченная клавиатура (только просмотр и ответ на уточнения)
            # TASK 17 Этап C: Локализованные кнопки
            if request.status == "Уточнение":
                # Если требуется уточнение - кнопка ответа
                reply_text = get_text("buttons.reply", language=lang) or "💬 Ответить"
                rows.append([InlineKeyboardButton(text=reply_text, callback_data=f"replyclarify_{request.request_number}")])
            # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"

            # Кнопка просмотра медиа (если есть)
            if has_media:
                view_media_text = get_text("buttons.view_media", language=lang) or "📎 Просмотр медиа"
                rows.append([InlineKeyboardButton(text=view_media_text, callback_data=f"view_request_media_{request.request_number}")])

        # Добавляем кнопку "Назад к списку"
        # TASK 17 Этап C: Локализованная кнопка
        data = await state.get_data()
        current_page = int(data.get("my_requests_page", 1))
        back_to_list_text = get_text("buttons.back_to_list", language=lang) or "🔙 Назад к списку"
        rows.append([InlineKeyboardButton(text=back_to_list_text, callback_data=f"back_list_{current_page}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} для пользователя {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("back_list_"))
async def handle_back_to_list(callback: CallbackQuery, state: FSMContext):
    """Возврат из деталей заявки к списку с восстановлением страницы и фильтра"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        # Восстанавливаем страницу из callback_data
        page = int(callback.data.replace("back_list_", ""))
        await state.update_data(my_requests_page=page)

        # Удаляем текущее сообщение с деталями
        await callback.message.delete()

        # Получаем данные пользователя
        telegram_id = callback.from_user.id
        data = await state.get_data()
        active_status = data.get("my_requests_status", "active")
        current_page = int(data.get("my_requests_page", 1))

        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            user = service.get_user_by_telegram_id(telegram_id)

            if not user:
                await callback.message.answer(get_text("common.user_not_found", language=lang))
                await callback.answer()
                return

            # Определяем роль пользователя (COD-01: канонический парсер, JSON+CSV)
            user_roles = parse_roles_safe(user.roles)

            active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

            # Получаем заявки в зависимости от роли
            has_active_shift = False
            executor_specializations = []
            if active_role == "executor":
                from datetime import datetime

                # Получаем специализации исполнителя (может быть несколько)
                if user.specialization:
                    try:
                        if isinstance(user.specialization, str) and user.specialization.startswith('['):
                            executor_specializations = json.loads(user.specialization)
                        else:
                            executor_specializations = [user.specialization]
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Ошибка парсинга специализации пользователя {user.id}: {e}")
                        executor_specializations = [user.specialization] if user.specialization else []

                # Проверяем, есть ли активная смена
                now = datetime.now()
                has_active_shift = service.get_active_shift(user.id, now) is not None

            # Подсчёт + БД-пагинация (ORM-логика в сервисе)
            ITEMS_PER_PAGE = 5
            offset = (current_page - 1) * ITEMS_PER_PAGE
            total_requests, requests = service.paginate_back_to_list(
                user=user,
                active_role=active_role,
                active_status=active_status,
                has_active_shift=has_active_shift,
                executor_specializations=executor_specializations,
                offset=offset,
                limit=ITEMS_PER_PAGE,
            )

        total_pages = (total_requests + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

        # TASK 17 Issue #5: Use localized helper functions for list formatting
        from uk_management_bot.utils.request_helpers import (
            format_requests_list_header,
            format_request_list_item,
            get_status_icon
        )

        if not requests:
            # Empty state message
            if active_role == "executor":
                title = get_text('requests.assigned_requests_title', language=lang)
                empty_msg = get_text('requests.no_assigned_requests', language=lang) or "У вас пока нет назначенных заявок."
                message_text = f"📋 <b>{title}</b>\n\n{empty_msg}"
            else:
                if active_status == "active":
                    title = get_text('requests.active_requests_title', language=lang)
                    empty_msg = get_text('requests.no_active_requests', language=lang) or "У вас пока нет активных заявок."
                elif active_status == "archive":
                    title = get_text('requests.archive_title', language=lang)
                    empty_msg = get_text('requests.no_archive_requests', language=lang) or "У вас пока нет заявок в архиве."
                else:
                    title = get_text('requests.all_filter', language=lang)
                    empty_msg = get_text('requests.no_requests', language=lang) or "У вас пока нет заявок."
                message_text = f"📋 <b>{title}</b>\n\n{empty_msg}"

            await callback.message.answer(message_text, parse_mode="HTML")
            await callback.answer()
            return

        # Format list header
        message_text = format_requests_list_header(
            total_requests=total_requests,
            current_page=current_page,
            total_pages=total_pages,
            status_filter=active_status,
            role=active_role,
            language=lang
        )

        # Для заявителей - текстовый список, для исполнителей - кнопки
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        if active_role != "executor":
            # Текстовый список для заявителей (используем helper-функцию)
            for i, req in enumerate(requests, 1):
                message_text += format_request_list_item(
                    request=req,
                    index=i,
                    language=lang,
                    show_details=True
                )
        else:
            # Кнопки для исполнителей
            # TASK 17 Этап A: Используем resolve_category_key и get_category_display для нормализации категорий
            from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
            for req in requests:
                icon = get_status_icon(req.status)
                category_key = resolve_category_key(req.category)
                category_display = get_category_display(category_key, language=lang)
                button_text = f"{icon} #{req.request_number} - {category_display}"
                builder.button(text=button_text, callback_data=f"view_request_{req.request_number}")

            builder.adjust(1)  # По одной кнопке в ряд

        # TASK 17 Issue #5: Localized pagination and filter buttons
        pagination_buttons = []
        if current_page > 1:
            back_text = get_text('buttons.back', language=lang)
            pagination_buttons.append(InlineKeyboardButton(text=f"◀️ {back_text}", callback_data=f"requests_page_{current_page - 1}"))
        if current_page < total_pages:
            forward_text = get_text('buttons.forward', language=lang)
            pagination_buttons.append(InlineKeyboardButton(text=forward_text, callback_data=f"requests_page_{current_page + 1}"))

        if pagination_buttons:
            builder.row(*pagination_buttons)

        # Добавляем фильтры только для не-исполнителей
        if active_role != "executor":
            all_text = get_text('requests.all_filter', language=lang)
            active_text = get_text('requests.active_filter', language=lang)
            archive_text = get_text('requests.archive_filter', language=lang)

            filter_buttons = [
                InlineKeyboardButton(text=f"📋 {all_text}" if active_status == "all" else f"⚪️ {all_text}", callback_data="requests_filter_all"),
                InlineKeyboardButton(text=f"🟢 {active_text}" if active_status == "active" else f"⚪️ {active_text}", callback_data="requests_filter_active"),
                InlineKeyboardButton(text=f"📦 {archive_text}" if active_status == "archive" else f"⚪️ {archive_text}", callback_data="requests_filter_archive")
            ]
            builder.row(*filter_buttons)

            # Добавляем кнопки для заявок, требующих действий заявителя
            reply_text = get_text('requests.reply_to_request', language=lang)
            for req in requests:
                if req.status == "Уточнение":
                    builder.row(InlineKeyboardButton(
                        text=f"💬 {reply_text} #{req.request_number}",
                        callback_data=f"replyclarify_{req.request_number}"
                    ))
                # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"

        await callback.message.answer(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)

@router.callback_query(F.data.regexp(_EDIT_REQUEST_NUMBER_RE))
async def handle_edit_request(callback: CallbackQuery, state: FSMContext):
    """Обработка редактирования заявки"""
    try:
        logger.info(f"Обработка редактирования заявки для пользователя {callback.from_user.id}")

        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            request_number = callback.data.replace("edit_", "")

            # Получаем заявку из базы данных
            request = service.get_request_by_number(request_number)

            if not request:
                await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
                return

            # Проверяем права доступа (сравниваем с telegram_id пользователя)
            user = service.get_user_by_telegram_id(callback.from_user.id)
            if not user or request.user_id != user.id:
                await callback.answer(get_text("requests.no_edit_permission", language=lang), show_alert=True)
                return

        # Сохраняем номер заявки в FSM для редактирования
        await state.update_data(editing_request_number=request_number)
        await state.set_state(RequestStates.category)

        await callback.message.edit_text(
            get_text("requests.edit_request_select_category", language=lang).format(request_number=request_number),
            reply_markup=get_categories_keyboard()
        )

        logger.info(f"Начато редактирование заявки {request_number} пользователем {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки редактирования заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)

# Менеджерское удаление заявки перенесено на префикс `mgr_delete_` и живёт в
# handlers/admin.py::handle_delete_request (гейт ADMIN_USER_IDS + каскадное удаление).
# Прежний bare-`delete_` owner-delete здесь затенял админский (requests_router
# регистрируется раньше admin_router) и к тому же удалял заявку без подтверждения.
# Удалён — см. test_bug_duty_assign_routing::test_admin_router_owns_mgr_delete.

# BUG-BOT-034/PR-25: менеджерское «Принять» (`accept_<NNN>`) живёт в
# handlers/admin.py::handle_accept_request (канон-переход через workflow_runner
# MANAGER_ASSIGN + has_admin_access). Прежний bare-`accept_` handler здесь —
# ручной `update_status_by_actor("В работе")` — затенял админский (requests_router
# раньше admin_router). Удалён; admin теперь единственный владелец строгого
# `^accept_\d{6}-\d{3,}$`. См. test_bug_duty_assign_routing::test_admin_router_owns_accept.

# Менеджерское завершение заявки перенесено на префикс `mgr_complete_` и живёт в
# handlers/admin.py::handle_complete_request (статус EXECUTED + AuditLog). Прежний
# bare-`complete_` исполнительский complete здесь затенял и админский менеджерский
# complete, и выделенный `complete_work_` (по префиксу). Исполнитель завершает
# через `executor_complete_` (ниже) и `complete_work_` (request_status_management).
# Удалён — см. test_bug_duty_assign_routing::{test_admin_router_owns_mgr_complete,
# test_complete_work_routes_to_status_management}.


# BUG-BOT-022: ранее здесь был дубликат handler-а `clarify_<NNN>`. Он
# регистрировался в requests_router (включается раньше admin_router) и
# перехватывал клик "❓ Уточнить" из admin request detail, после чего падал
# в generic "Ошибка" (status update flow без интерактивного prompt-а).
# Полноценный handler с FSM-flow (prompt → text input → notify applicant)
# живёт в `uk_management_bot/handlers/admin.py::handle_clarify_request`.
# Дубликат удалён — теперь клик корректно попадает в admin-handler.


# BUG-BOT-034/PR-25: менеджерский «Закуп» (`purchase_<NNN>`) живёт в
# handlers/admin.py::handle_purchase_request (открывает ввод материалов через
# RequestStatusStates.waiting_for_materials, статус НЕ меняет до ввода). Прежний
# bare-`purchase_` handler здесь преждевременно ставил «Закуп» без ввода материалов
# и затенял админский (requests_router раньше admin_router). Удалён; admin —
# единственный владелец строгого `^purchase_\d{6}-\d{3,}$`.
# См. test_bug_duty_assign_routing::test_admin_router_owns_purchase.


# BUG-BOT-030: ранее использовался prefix-match `cancel_` с поддерживаемым exclusion list,
# что приводило к anti-pattern (open-set, ловит любые новые cancel_-callback).
# Заменено на строгий regex по формату request_number. BUG-122: матчер теперь
# собран из shared REQUEST_NUMBER_CORE (\d{3,}) — определён выше, у импортов.
@router.callback_query(F.data.regexp(_CANCEL_REQUEST_NUMBER_RE.pattern))
async def handle_cancel_request(callback: CallbackQuery, state: FSMContext):
    """Обработка отмены заявки. Срабатывает только на `cancel_<YYMMDD-NNN>`."""
    try:
        # Менеджер или владелец (в RequestService также есть проверка)
        request_number = callback.data.replace("cancel_", "")
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

            service = RequestService(db_session)
            result = service.update_status_by_actor(
                request_number=request_number,
                new_status="Отменена",
                actor_telegram_id=callback.from_user.id,
            )
            if not result.get("success"):
                error_msg = result.get("message", get_text("common.error", language=lang))
                await callback.answer(error_msg, show_alert=True)
                return
            await callback.message.edit_text(
                get_text("requests.request_cancelled", language=lang).format(request_number=request_number),
                reply_markup=get_main_keyboard(language=lang)
            )
    except Exception as e:
        logger.error(f"Ошибка обработки отмены заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)


# Менеджерское «Отклонить» перенесено на префикс `mgr_deny_` и живёт в
# handlers/admin.py::handle_deny_request (FSM «ввод причины отклонения»). Прежний
# bare-`deny_` handler здесь («исполнитель предлагает отказ») затенял менеджерский
# (requests_router раньше admin_router): клик менеджера давал «предложение отказа
# отправлено» вместо запроса причины. Фича propose-deny сейчас без кнопки; если
# понадобится — завести отдельный префикс `executor_deny_` + кнопку.
# Удалён — см. test_bug_duty_assign_routing::test_admin_router_owns_mgr_deny.


@router.callback_query(F.data.regexp(_APPROVE_REQUEST_NUMBER_RE))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выполненной заявки заявителем.

    SSOT-кластер #1, PR2c: канон требует оценку при приёмке (APPLICANT_ACCEPT
    с rating, только из «Исполнено»). Прежняя прямая запись «Принято» без
    рейтинга снята — кнопка теперь ведёт в канонический rated-accept: показываем
    клавиатуру оценки 1–5★, дальнейшую приёмку выполняет
    request_acceptance.save_rating через run_command(APPLICANT_ACCEPT).
    """
    try:
        request_number = callback.data.replace("approve_", "")
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        from uk_management_bot.keyboards.admin import get_rating_keyboard
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.rate_request", language=lang),
            reply_markup=get_rating_keyboard(request_number),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка обработки подтверждения заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)


# ============================
# Мои заявки (список + пагинация)
# ============================

