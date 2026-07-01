"""«Мои заявки»: список, фильтры (статус/категория/период/исполнитель), ответ на уточнение."""

from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from uk_management_bot.services.request_handler_service import RequestHandlerService

from uk_management_bot.keyboards.requests import (
    get_cancel_keyboard,
    get_status_filter_inline_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_user_contextual_keyboard
import logging
from uk_management_bot.services.request_service import RequestService

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.status_display import get_status_display as _sd_get_status_display, STATUS_EMOJI
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix

from ._router import router

from .shared import (
    _db_scope,
    RequestStates,
    MY_REQUESTS_TEXTS,
)

logger = logging.getLogger(__name__)


@router.message(F.text.in_(MY_REQUESTS_TEXTS))
async def show_my_requests(message: Message, state: FSMContext):
    """Показать список заявок пользователя (страница 1)"""
    try:
        telegram_id = message.from_user.id
        # Читаем активный фильтр и страницу из FSM
        data = await state.get_data()
        active_status = data.get("my_requests_status", "all")  # По умолчанию показываем все заявки
        current_page = int(data.get("my_requests_page", 1))

        # Убеждаемся, что статус установлен в FSM
        if not data.get("my_requests_status"):
            await state.update_data(my_requests_status="all")
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(message.from_user.id, db_session)

            # Получаем пользователя из базы данных по telegram_id
            user = service.get_user_by_telegram_id(telegram_id)

            if not user:
                await message.answer(get_text("common.user_not_found", language=lang))
                return

            # Определяем роль пользователя
            user_roles = []
            if user.roles:
                try:
                    import json
                    user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Ошибка парсинга ролей пользователя {user.id}: {e}")
                    user_roles = []

            active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

            # Логируем начало запроса
            logger.info(f"show_my_requests: telegram_id={telegram_id}, active_role={active_role}, active_status={active_status}, user_id={user.id}")

            # Заявки в зависимости от роли + status-фильтр + сортировка (ORM в сервисе).
            # Семантика идентична прежней (executor-active = В работе/Закуп/
            # Уточнение; non-executor all = case-приоритет активных).
            user_requests = service.list_my_requests(user, active_role, active_status)

            # Добавляем логирование для отладки
            logger.info(f"Пользователь {telegram_id} (роль: {active_role}) - найдено заявок: {len(user_requests)}")
            if user_requests:
                logger.info(f"Первые 3 заявки: {[(r.request_number, r.status, r.category) for r in user_requests[:3]]}")
            if active_role == "executor" and len(user_requests) == 0:
                # Проверяем, есть ли вообще назначения для сантехников (диагностика)
                test_count = service.count_plumber_group_test_requests()
                logger.info(f"Тестовый запрос для сантехников вернул {test_count} заявок")

        total_requests = len(user_requests)
        requests_per_page = 5
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        # Корректируем текущую страницу, если вышла за диапазон
        if current_page > total_pages:
            current_page = total_pages

        start_idx = (current_page - 1) * requests_per_page
        end_idx = start_idx + requests_per_page
        page_requests = user_requests[start_idx:end_idx]

        # TASK 17 Issue #5: Use localized helper functions for formatting
        from uk_management_bot.utils.request_helpers import (
            format_requests_list_header,
            format_request_list_item,
            get_status_icon
        )

        # Use helper function for list header
        message_text = format_requests_list_header(
            total_requests=total_requests,
            current_page=current_page,
            total_pages=total_pages,
            status_filter=active_status,
            role=active_role,
            language=lang
        )

        if not page_requests:
            if active_role == "executor":
                no_requests_msg = get_text('requests.no_assigned_requests', language=lang) or "У вас пока нет назначенных заявок."
                message_text += no_requests_msg
            else:
                no_requests_msg = get_text('requests.no_requests', language=lang) or "У вас пока нет заявок."
                message_text += no_requests_msg
        else:
            # Для заявителей показываем текстовый список (используем helper-функцию)
            if active_role != "executor":
                for i, r in enumerate(page_requests, 1):
                    message_text += format_request_list_item(
                        request=r,
                        index=i,
                        language=lang,
                        show_details=True
                    )

        from uk_management_bot.keyboards.requests import get_pagination_keyboard

        # Формируем клавиатуру
        rows = []

        # Для исполнителей НЕ показываем кнопки фильтрации (Активные/Архив)
        # Они видят только заявки, назначенные им
        if active_role != "executor":
            # Для заявителей и других ролей - показываем фильтры
            filter_status_kb = get_status_filter_inline_keyboard(active_status, language=lang)
            rows = list(filter_status_kb.inline_keyboard)

            # TASK 17 Issue #5: Localized reply button
            reply_text = get_text('requests.reply_to_request', language=lang)
            for r in page_requests:
                if r.status == "Уточнение":
                    # Кнопка для ответа на уточнение
                    rows.append([InlineKeyboardButton(
                        text=f"💬 {reply_text} #{r.request_number}",
                        callback_data=f"replyclarify_{r.request_number}"
                    )])
                # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"
        else:
            # Для исполнителей добавляем кнопки заявок
            for i, r in enumerate(page_requests, 1):
                icon = get_status_icon(r.status)
                from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
                cat_display = get_category_display(resolve_category_key(r.category), language=lang)
                button_text = f"{icon} #{r.request_number} - {cat_display}"
                rows.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_request_{r.request_number}"
                )])

        # TASK 17 Issue #5: Add language parameter to pagination keyboard
        pagination_kb = get_pagination_keyboard(current_page, total_pages, language=lang)
        rows += pagination_kb.inline_keyboard
        combined = InlineKeyboardMarkup(inline_keyboard=rows)
        # Сохраняем актуальную страницу в FSM
        await state.update_data(my_requests_page=current_page)
        try:
            await message.answer(message_text, reply_markup=combined)
        except TelegramBadRequest:
            # повторное нажатие на тот же фильтр — просто обновим сообщением
            await message.answer(message_text, reply_markup=combined)
    except Exception as e:
        logger.error(f"Ошибка отображения списка заявок для пользователя {message.from_user.id}: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("requests.error_loading_requests", language=lang))


@router.message(Command("my_requests"))
async def cmd_my_requests(message: Message, state: FSMContext):
    """Команда /my_requests показывает страницу 1 списка заявок"""
    # По умолчанию показываем активные
    await state.update_data(my_requests_status="active")
    await show_my_requests(message, state)


@router.callback_query(F.data.startswith("replyclarify_"))
async def handle_reply_clarify_start(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет ответить на запрос уточнения. Просим ввести текст."""
    try:
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            request_number = callback.data.replace("replyclarify_", "")
            # Показать текущий диалог из notes перед вводом
            req = service.get_request_by_number(request_number)
            await state.update_data(reply_request_number=request_number)
            await state.set_state(RequestStates.waiting_clarify_reply)
            # Получаем пользователя из базы данных по telegram_id
            user = service.get_user_by_telegram_id(callback.from_user.id)

            if req and user and req.user_id == user.id:
                notes_text = (req.notes or "").strip()
                if notes_text:
                    await callback.message.answer(get_text("requests.current_dialog", language=lang).format(notes=notes_text))
                else:
                    await callback.message.answer(get_text("requests.dialog_empty", language=lang))
        await callback.message.answer(
            get_text("requests.enter_clarification_reply", language=lang),
            reply_markup=get_cancel_keyboard(language=lang),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка старта ответа на уточнение: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang))


@router.message(RequestStates.waiting_clarify_reply)
async def handle_reply_clarify_text(message: Message, state: FSMContext):
    """Сохраняем ответ пользователя в notes без смены статуса."""
    try:
        with _db_scope(None) as db_session:
            handler_service = RequestHandlerService(db_session)
            lang = get_user_language(message.from_user.id, db_session)

            data = await state.get_data()
            request_number = data.get("reply_request_number")
            if not request_number:
                await message.answer(get_text("requests.request_number_not_found", language=lang))
                await state.clear()
                return

            service = RequestService(db_session)
            req = service.get_request_by_number(request_number)
            # Получаем пользователя из базы данных по telegram_id
            user = handler_service.get_user_by_telegram_id(message.from_user.id)

            if not req or not user or req.user_id != user.id:
                await message.answer(get_text("requests.request_not_found_or_unavailable", language=lang))
                await state.clear()
                await message.answer(get_text("common.return_to_menu", language=lang), reply_markup=get_user_contextual_keyboard(message.from_user.id))
                return
            existing = (req.notes or "").strip()
            to_add = message.text.strip()
            # Добавляем с ролью пользователя
            user_prefix = get_text("requests.user_prefix", language=lang)
            clarification_label = get_text("requests.clarification_label", language=lang)
            new_notes = (existing + "\n" if existing else "") + f"[{user_prefix}] {clarification_label}: {to_add}"
            handler_service.append_clarify_reply(req, new_notes)
        await message.answer(get_text("requests.reply_saved", language=lang), reply_markup=get_main_keyboard(language=lang))
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка сохранения ответа на уточнение: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await state.clear()
        await message.answer(get_text("requests.reply_save_failed", language=lang), reply_markup=get_main_keyboard(language=lang))


@router.callback_query(F.data.startswith("status_"))
async def handle_status_filter(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра статуса для списка заявок"""
    try:
        # Совместимость с тестами: поддержать текстовые статусы, но маппить на упрощённые "active"/"archive"/"all"
        raw = callback.data.replace("status_", "")
        if raw in ("active", "archive", "all"):
            choice = raw
        elif raw == "В работе":
            choice = "В работе"
        else:
            choice = raw
        # Запоминаем фильтр и сбрасываем страницу
        await state.update_data(my_requests_status=choice, my_requests_page=1)

        # Собираем список заявок и клавиатуру, затем редактируем сообщение
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)

            # Получаем пользователя из базы данных по telegram_id
            user = service.get_user_by_telegram_id(callback.from_user.id)

            lang = get_user_language(callback.from_user.id, db_session)

            if not user:
                await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
                return

            # Фильтр + сортировка списка (ORM в сервисе, семантика идентична).
            user_requests = service.list_applicant_requests_filtered(user.id, choice)
        current_page = 1
        requests_per_page = 5
        total_pages = max(1, (len(user_requests) + requests_per_page - 1) // requests_per_page)
        page_requests = user_requests[:requests_per_page]

        # Определяем заголовок в зависимости от фильтра
        if choice == "active":
            status_title = get_text("requests.handlers.active_requests_title", language=lang)
        elif choice == "archive":
            status_title = get_text("requests.handlers.archive_requests_title", language=lang)
        else:
            status_title = get_text("requests.handlers.all_requests_title", language=lang)
        message_text = get_text("requests.handlers.requests_list_page_header", language=lang).format(
            title=status_title, current_page=current_page, total_pages=total_pages
        )
        if not page_requests:
            message_text += get_text("requests.handlers.no_requests_hint", language=lang)
        else:
            for i, request in enumerate(page_requests, 1):
                from uk_management_bot.utils.address_helpers import localize_address
                address = localize_address(request.address, lang)
                if len(address) > 60:
                    address = address[:60] + "…"
                # TASK 17 Этап A и C: Локализуем категорию и статус через status_display.py
                from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
                category_key = resolve_category_key(request.category)
                category_display = get_category_display(category_key, language=lang)
                status_display = _sd_get_status_display(request.status, language=lang)
                icon = STATUS_EMOJI.get(request.status, "📋")
                message_text += f"{i}. {icon} #{request.request_number} - {category_display} - {status_display}\n"
                # TASK 17 Этап C: Локализованные метки
                address_label = get_text("requests.address_label", language=lang) or "Адрес"
                created_label = get_text("requests.created_label", language=lang) or "Создана"
                message_text += f"   {address_label} {address}\n"
                message_text += f"   {created_label} {request.created_at.strftime('%d.%m.%Y')}\n"
                if choice == "archive" and request.status == "Отменена" and request.notes:
                    # TASK 17 Этап C: Локализованная метка
                    reason_label = get_text("requests.cancellation_reason_label", language=lang) or "Причина отказа"
                    message_text += f"   {reason_label} {request.notes}\n"
                elif request.status == "Уточнение" and request.notes:
                    # TASK 17 Этап C: Локализованная метка
                    clarification_label = get_text("requests.clarification_label", language=lang) or "Уточнение"
                    # Показываем последние сообщения из диалога уточнения
                    notes_lines = request.notes.strip().split('\n')
                    last_messages = [line for line in notes_lines[-3:] if line.strip()]  # Последние 3 сообщения
                    if last_messages:
                        preview = '\n'.join(last_messages)
                        if len(preview) > 100:
                            preview = preview[:97] + '...'
                        message_text += f"   {clarification_label}: {preview}\n"
                message_text += "\n"

        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        filter_status_kb = get_status_filter_inline_keyboard(choice, language=lang)

        # Формируем клавиатуру
        combined_rows = list(filter_status_kb.inline_keyboard)

        # Добавляем кнопки для заявок, требующих действий заявителя
        for r in page_requests:
            if r.status == "Уточнение":
                # Кнопка для ответа на уточнение
                combined_rows.append([InlineKeyboardButton(
                    text=get_text("requests.handlers.reply_to", language=lang).format(number=r.request_number),
                    callback_data=f"replyclarify_{r.request_number}"
                )])
            # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"

        # Добавляем пагинацию
        pagination_kb = get_pagination_keyboard(current_page, total_pages)
        combined_rows += pagination_kb.inline_keyboard
        combined = type(pagination_kb)(inline_keyboard=combined_rows)

        try:
            await callback.message.edit_text(message_text, reply_markup=combined)
        except TelegramBadRequest:
            # Повторное нажатие по тому же фильтру/такому же тексту — просто ответим без алерта
            pass
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра статуса: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("categoryfilter_"))
async def handle_category_filter(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора фильтра категории
    
    TASK 17 Этап A: Теперь работает с внутренними ключами категорий вместо русских текстов.
    """
    try:
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        # TASK 17 Этап A: Извлекаем внутренний ключ категории (или "all")
        choice = callback.data.replace("categoryfilter_", "")
        # choice теперь содержит внутренний ключ (например, "electricity") или "all"
        await state.update_data(my_requests_category=choice, my_requests_page=1)
        fake_message = callback.message
        fake_message.from_user = callback.from_user
        await show_my_requests(fake_message, state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра категории: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)


@router.callback_query(F.data == "filters_reset")
async def handle_filters_reset(callback: CallbackQuery, state: FSMContext):
    """Сброс всех фильтров списка заявок"""
    try:
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        await state.update_data(
            my_requests_status="all",
            my_requests_category="all",
            my_requests_period="all",
            my_requests_executor="all",
            my_requests_page=1,
        )
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer(get_text("requests.filters_reset", language=lang))
    except Exception as e:
        logger.error(f"Ошибка сброса фильтров: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("period_"))
async def handle_period_filter(callback: CallbackQuery, state: FSMContext):
    try:
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        choice = callback.data.replace("period_", "")
        await state.update_data(my_requests_period=choice, my_requests_page=1)
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра периода: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("executorfilter_"))
async def handle_executor_filter(callback: CallbackQuery, state: FSMContext):
    try:
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        choice = callback.data.replace("executorfilter_", "")
        await state.update_data(my_requests_executor=choice, my_requests_page=1)
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра исполнителя: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)


