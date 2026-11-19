"""Менеджер: просмотр заявок, медиа, подтверждение, пагинация."""
import html

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.fsm.context import FSMContext
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
# AUD6-P1-6: адресные уведомления — той же матрицей интентов, что API-путь
# (одни получатели, один текст); канальная лента — отдельным хелпером.
from uk_management_bot.services.workflow_notifications import (
    dispatch_notify_intents_sync,
    notify_channel_status_changed,
)
from uk_management_bot.utils.workflow_predicates import (
    is_awaiting_applicant,
    is_awaiting_manager,
)

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display
from uk_management_bot.keyboards.requests import (
    get_category_display,
    get_discussion_rows,
    get_urgency_display,
    resolve_category_key,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.integrations import get_media_client
from uk_management_bot.services.request_media_entries import parse_media_entries, send_media_entries
from uk_management_bot.services.completion_media import get_completion_media_entries
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.utils.user_names import display_name, full_name
from uk_management_bot.keyboards.admin import ManagerListCb
from uk_management_bot.utils.request_workflow.projections import normalize_status
from uk_management_bot.utils.request_workflow.types import STATUS_RETURNED
from uk_management_bot.states.request_acceptance import ManagerAcceptanceStates

from ._router import router
from .elevator_hint import send_elevator_hint
from .lists import _MANAGER_LISTS, build_manager_list, edit_quiet
from .shared import already_handled_text, close_prompt, delete_admin_ids, remember_prompt

logger = logging.getLogger(__name__)


# ===== ОБРАБОТЧИКИ ПРОСМОТРА ЗАЯВОК ДЛЯ МЕНЕДЖЕРОВ =====

async def _answer_already_handled(callback: CallbackQuery, request_number: str, lang: str,
                                  *, _db=None) -> None:
    """Канон отказал в переходе — значит, заявку уже кто-то обработал.

    Карточку-решение получают все менеджеры: один подтвердил, второй жмёт ту же
    кнопку на своей копии. Вместо общего «ошибка подтверждения» — что с заявкой
    сейчас, а устаревшие кнопки заменяются одной «Открыть»: повторное нажатие
    не должно снова вести в отказ.
    """
    await callback.answer(
        await already_handled_text(request_number, lang, _db=_db), show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=get_text("notifications.workflow.btn_open_request", language=lang),
                callback_data=f"mview_{request_number}")]]))
    except TelegramAPIError as exc:  # отказ уже показан; кнопки — косметика
        logger.info("Кнопки устаревшей карточки %s не обновлены: %s",
                    request_number, type(exc).__name__)


def _back_row(request_number: str, back, lang: str) -> list:
    """«Назад к списку»: на ту же страницу, если карточку открыли из списка."""
    target = f"mreq_page_{back[0]}_{back[1]}" if back else f"mreq_back_{request_number}"
    return [InlineKeyboardButton(
        text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data=target)]


def _copy_row(request_number: str, applicant_phone, lang: str) -> list:
    """Кнопки копирования: номер заявки и телефон заявителя (если он есть).

    Нажатие кладёт текст в буфер на телефоне менеджера — выделять номер
    пальцем в сообщении больше не нужно. Запроса к боту при этом нет.
    """
    row = [InlineKeyboardButton(
        text=get_text("admin.keyboards.copy_number", language=lang),
        copy_text=CopyTextButton(text=request_number))]
    if applicant_phone:
        row.append(InlineKeyboardButton(
            text=get_text("admin.keyboards.copy_phone", language=lang),
            copy_text=CopyTextButton(text=str(applicant_phone))))
    return row


def build_manager_card_keyboard(request, *, active_assignment, has_media: bool, roles,
                                viewer_id: int, lang: str, back=None,
                                applicant_phone=None) -> InlineKeyboardMarkup:
    """Клавиатура карточки заявки менеджера по состоянию заявки.

    Ветки: ждёт заявителя → напомнить/принять за него; ждёт проверки менеджером
    → подтвердить/вернуть; возвращена жителем → принять (возврат необоснован)/
    вернуть; иначе — действия, которые канон пускает из текущего статуса.
    ``back`` — ``(вид списка, страница)``, если карточку открыли из списка.
    """
    from uk_management_bot.keyboards.admin import (
        get_change_category_button_row,
        get_manager_completed_request_actions_keyboard,
        get_manager_request_actions_keyboard,
        get_reassign_button_row,
        get_unaccepted_request_actions_keyboard,
    )

    number = request.request_number
    canon = normalize_status(request)
    media_row = [InlineKeyboardButton(
        text=get_text("admin.handlers.btn_media", language=lang), callback_data=f"media_{number}")]
    discussion = get_discussion_rows(
        number, has_report=bool(request.completion_report), language=lang)

    if is_awaiting_applicant(request):
        rows = list(get_unaccepted_request_actions_keyboard(number, language=lang).inline_keyboard)
        # Последняя строка — «назад к списку непринятых»: меняем на возврат на страницу.
        own_back = rows.pop()
        if has_media:
            rows.append(media_row)
        rows.extend(discussion)
        rows.append(_copy_row(number, applicant_phone, lang))
        rows.append(_back_row(number, back, lang) if back else own_back)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    returned = canon == STATUS_RETURNED
    if is_awaiting_manager(request) or returned:
        # «Принять (возврат необоснован)» = MANAGER_FORCE_ACCEPT, канон пускает
        # его только из «Возвращена»/«Исполнено»; «Выполнена» подтверждается
        # MANAGER_CONFIRM — поэтому is_returned берём из канона, а не из флага.
        rows = list(get_manager_completed_request_actions_keyboard(
            number, is_returned=returned, language=lang).inline_keyboard)
        if has_media:
            rows.append(media_row)
        rows.extend(discussion)
        rows.append(_copy_row(number, applicant_phone, lang))
        rows.append(_back_row(number, back, lang))
        return InlineKeyboardMarkup(inline_keyboard=rows)

    rows = list(get_manager_request_actions_keyboard(
        number, has_media=has_media, language=lang, status=canon,
        assigned=bool(active_assignment) or request.executor_id is not None,
        can_delete=viewer_id in delete_admin_ids(),
    ).inline_keyboard)
    # Переназначение — только при активном назначении и подходящем статусе.
    # Легаси до миграции 011: строки назначения нет, а исполнитель у заявки
    # есть — канон её переназначить пускает.
    rows.extend(row for row in (
        get_reassign_button_row(
            number,
            assignment_type=active_assignment.assignment_type if active_assignment else None,
            status=request.status, has_executor=request.executor_id is not None,
            roles=roles, language=lang),
        # Смена категории (решение владельца 2026-09-03): любой нетерминальный
        # статус, только менеджер.
        get_change_category_button_row(number, status=request.status, roles=roles, language=lang),
    ) if row)
    rows.extend(discussion)
    rows.append(_copy_row(number, applicant_phone, lang))
    rows.append(_back_row(number, back, lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("mview_"))
@router.callback_query(ManagerListCb.filter())
async def handle_manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", callback_data: ManagerListCb = None):
    """Карточка заявки менеджера.

    Два входа: `ml:<вид>:<страница>:<номер>` из списка — тогда «Назад» вернёт на
    ту же страницу; `mview_<номер>` — старые сообщения и переходы из других
    экранов. Хендлер один на оба фильтра: второй async-хендлер с sync-сессией
    гейт AUD3-07 не пускает.
    """
    try:
        lang = language
        logger.info(f"Обработка просмотра заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return

        back = None
        if callback_data is not None:
            request_number = callback_data.num
            if callback_data.kind in _MANAGER_LISTS:
                back = (callback_data.kind, callback_data.page)
        else:
            request_number = callback.data.replace("mview_", "")

        svc = AdminHandlerService(db)
        # Получаем заявку из базы данных
        request = svc.get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем информацию о пользователе, создавшем заявку
        request_user = svc.get_user_by_id(request.user_id)
        # A9-P2-2: карточка уходит с parse_mode=HTML (дефолт бота) — всё, что
        # ввёл пользователь (имя из Telegram-профиля, адрес, описание,
        # примечания с ответами на уточнения), экранируется в точке вывода.
        # Сырой '<a href>' становился живой ссылкой, одиночный '<'/'&' давал
        # Telegram-400, и менеджер не мог открыть заявку (класс BUG-174/178).
        if request_user:
            name = full_name(request_user)
            user_info = html.escape(name) if name else get_text("admin.handlers.user_by_id", language=lang).format(telegram_id=request_user.telegram_id)
        else:
            user_info = get_text("admin.handlers.unknown_user", language=lang)
        
        # Формируем детальную информацию о заявке
        message_text = get_text("admin.handlers.request_detail_header", language=lang).format(request_number=request.request_number) + "\n\n"
        message_text += get_text("admin.handlers.request_detail_applicant", language=lang).format(user_info=user_info) + "\n"
        message_text += get_text("admin.handlers.request_detail_telegram_id", language=lang).format(telegram_id=request_user.telegram_id if request_user else 'N/A') + "\n"
        category_display = get_category_display(resolve_category_key(request.category), language=lang)
        urgency_display = get_urgency_display(request.urgency, language=lang) if request.urgency else ""
        message_text += get_text("admin.handlers.request_detail_category", language=lang).format(category=category_display) + "\n"
        message_text += get_text("admin.handlers.request_detail_status", language=lang).format(status=get_status_display(request.status, language=lang)) + "\n"
        message_text += get_text("admin.handlers.request_detail_address", language=lang).format(address=html.escape(request.address or "")) + "\n"
        message_text += get_text("admin.handlers.request_detail_description", language=lang).format(description=html.escape(request.description or "")) + "\n"
        message_text += get_text("admin.handlers.request_detail_urgency", language=lang).format(urgency=urgency_display) + "\n"
        if request.apartment:
            message_text += get_text("admin.handlers.request_detail_apartment", language=lang).format(apartment=html.escape(str(request.apartment))) + "\n"
        message_text += get_text("admin.handlers.request_detail_created", language=lang).format(created_at=request.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"
        if request.updated_at:
            message_text += get_text("admin.handlers.request_detail_updated", language=lang).format(updated_at=request.updated_at.strftime('%d.%m.%Y %H:%M')) + "\n"

        # Добавляем информацию о назначении
        active_assignment = svc.get_active_assignment(request.request_number)

        if active_assignment:
            if active_assignment.assignment_type == "group":
                # Групповое назначение (дежурному специалисту)
                spec_name = get_text(f"specializations.{active_assignment.group_specialization}", language=lang) if active_assignment.group_specialization else active_assignment.group_specialization
                message_text += get_text("admin.handlers.assigned_duty_specialist", language=lang).format(spec_name=spec_name) + "\n"
            elif active_assignment.assignment_type == "individual" and active_assignment.executor_id:
                # Индивидуальное назначение конкретному исполнителю
                assigned_executor = svc.get_user_by_id(active_assignment.executor_id)
                if assigned_executor:
                    executor_name = html.escape(display_name(assigned_executor))
                    message_text += get_text("admin.handlers.assigned_executor", language=lang).format(executor_name=executor_name) + "\n"

        if request.notes:
            message_text += get_text("admin.handlers.request_detail_notes", language=lang).format(notes=html.escape(request.notes)) + "\n"

        # Проверяем наличие медиафайлов. Фотоотчёт: SSOT — media-service
        # (дашборд/TWA грузят туда, минуя legacy-поле), фолбэк — completion_media.
        media_files = request.media_files if request.media_files else []
        completion_media = await get_completion_media_entries(
            request.request_number, request.completion_media
        )
        has_media = len(media_files) > 0 or len(completion_media) > 0

        # Для ожидающих приёмки заявителем — сколько уже ждём.
        if is_awaiting_applicant(request):
            from datetime import datetime, timezone
            completed_at = request.completed_at if request.completed_at else request.updated_at
            if completed_at:
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(tzinfo=timezone.utc)
                waiting_time = datetime.now(timezone.utc) - completed_at
                days = waiting_time.days
                hours = waiting_time.seconds // 3600
                minutes = (waiting_time.seconds % 3600) // 60

                if days > 0:
                    time_str = f"{days}д {hours}ч"
                elif hours > 0:
                    time_str = f"{hours}ч {minutes}м"
                else:
                    time_str = f"{minutes}м"

                message_text += "\n" + get_text("admin.handlers.waiting_acceptance", language=lang).format(time_str=time_str) + "\n"

        keyboard = build_manager_card_keyboard(
            request, active_assignment=active_assignment, has_media=has_media,
            roles=roles, viewer_id=callback.from_user.id, lang=lang, back=back,
            applicant_phone=request_user.phone if request_user else None)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("media_"))
async def handle_view_request_media(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка просмотра медиафайлов заявки"""
    try:
        lang = language

        logger.info(f"Просмотр медиафайлов заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_media", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("media_", "")

        # Получаем заявку из базы данных
        request = AdminHandlerService(db).get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем наличие медиафайлов и парсим JSON
        import json

        media_files = []
        if request.media_files:
            try:
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга media_files для заявки {request.request_number}: {e}")

        # Фотоотчёт: SSOT — media-service, фолбэк — legacy-поле (парсинг
        # JSON-строки/dict'ов внутри сервиса). Элементы — MediaEntry.
        completion_media = await get_completion_media_entries(
            request.request_number, request.completion_media
        )

        if not media_files and not completion_media:
            await callback.answer(get_text("admin.handlers.no_media_attached", language=lang), show_alert=True)
            return

        # Отправляем медиафайлы при создании заявки
        if media_files:
            await callback.message.answer(
                get_text("admin.handlers.media_creation_header", language=lang).format(request_number=request.request_number),
                parse_mode="HTML"
            )
            # services/request_media_entries.py: три формы элементов (в т.ч.
            # файлы медиа-сервиса байтами), чанки по лимиту Telegram.
            entries = parse_media_entries(media_files)
            first_caption = (
                get_text("admin.handlers.photo_counter", language=lang).format(current=1, total=len(entries))
                if len(entries) > 1 else None
            )
            try:
                sent = await send_media_entries(
                    callback.message, entries, get_media_client(), first_caption=first_caption
                )
            except TelegramAPIError as e:
                # Устаревший file_id и т.п.: как и раньше — сообщение, не падение.
                logger.error("Ошибка отправки медиафайлов заявки %s: %s", request.request_number, e)
                sent = 0
            if sent == 0:
                await callback.message.answer(get_text("admin.handlers.media_send_failed", language=lang))

        # Отправляем медиафайлы при завершении заявки
        if completion_media:
            await callback.message.answer(
                get_text("admin.handlers.media_completion_header", language=lang).format(request_number=request.request_number),
                parse_mode="HTML"
            )

            # Файлы media-service — байтами (его file_id основному боту не
            # годятся), чанки по лимиту Telegram — внутри send_media_entries.
            counter_key = (
                "admin.handlers.file_counter" if completion_media[0].kind == "document"
                else "admin.handlers.photo_counter"
            )
            first_caption = (
                get_text(counter_key, language=lang).format(current=1, total=len(completion_media))
                if len(completion_media) > 1 else None
            )
            try:
                sent = await send_media_entries(
                    callback.message, completion_media, get_media_client(), first_caption=first_caption
                )
            except TelegramAPIError as e:
                logger.error("Ошибка отправки фотоотчёта заявки %s: %s", request.request_number, e)
                sent = 0
            if sent == 0:
                await callback.message.answer(get_text("admin.handlers.media_send_failed", language=lang))

        await callback.answer(get_text("admin.handlers.media_sent", language=lang))
        logger.info(f"Отправлены медиафайлы заявки {request.request_number} менеджеру {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов заявки: {e}")
        await callback.answer(get_text("admin.handlers.error_loading_media", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("confirm_completed_"))
async def handle_manager_confirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер подтверждает выполнение заявки"""
    try:
        lang = language

        logger.info(f"Подтверждение выполнения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("confirm_completed_", "")

        # Канонический переход через единый layer (PR2a): run_command владеет
        # своей транзакцией (свежая сессия + FOR UPDATE + ActorContext из БД +
        # patch/audit/outbox в одной tx). Пишет СРАЗУ канон: Выполнена→Исполнено.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_CONFIRM, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_CONFIRM отклонён для {request_number}: {e}")
            await _answer_already_handled(callback, request_number, lang)
            return
        if getattr(outcome, "no_op", False):
            # MANAGER_CONFIRM — no_op_if_same: заявка уже «Исполнено», канон
            # ничего не менял и ошибкой это не считает. Карточку получают все
            # менеджеры, второе нажатие — обычное дело; без этой ветки оно
            # выглядело успехом и повторно писало жителю «заявка выполнена».
            logger.info(f"MANAGER_CONFIRM для {request_number}: уже подтверждена (no_op)")
            await _answer_already_handled(callback, request_number, lang)
            return

        # Best-effort post-commit (потеря допустима, PR0 Р7): уведомления + правка.
        # run_command работал в своей сессии → перечитываем заявку свежей.
        request = AdminHandlerService(db).get_request_by_number(request_number)

        # Адресно — по матрице интентов (не бросает); в канал — хелпером.
        await dispatch_notify_intents_sync(
            db, request_number, outcome.post_commit_intents, bot=callback.bot)
        await notify_channel_status_changed(
            callback.bot, request, outcome.old_status, outcome.public_status)

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user if request else None
        if applicant and applicant.telegram_id:
            try:
                bot = callback.bot

                notification_text = get_text("admin.handlers.notify_applicant_completed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о подтверждении заявки {request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_confirmed", language=lang).format(request_number=request_number)
        )
        # Ф4a-2 (T7): подсказка о лифте уходит ПОСЛЕ общего try — иначе её сбой
        # дал бы rollback + «ошибка подтверждения» при уже закоммиченном MANAGER_CONFIRM.
        hint_target = (getattr(request, "elevator_id", None), request_number)

        logger.info(f"Заявка {request_number} подтверждена менеджером {user.id} (canon)")

    except Exception as e:
        logger.error(f"Ошибка подтверждения выполнения заявки: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)
        return

    await _safe_send_hint(callback, hint_target, lang)


async def _safe_send_hint(callback: CallbackQuery, hint_target: tuple, lang: str) -> None:
    """Best-effort подсказка о статусе лифта после подтверждения (Ф4a-2, T7).

    ``send_elevator_hint`` сам глотает SQLAlchemy/Telegram-сбои; здесь узкий
    перехват остального ожидаемого (ошибка данных/рантайма при сборке текста),
    чтобы сбой подсказки не долетел до глобального error-хендлера как «ошибка»
    уже успешного подтверждения. Текст исключения не логируем (соседство с Bot API).
    """
    elevator_id, request_number = hint_target
    try:
        await send_elevator_hint(
            callback.bot, callback.from_user.id,
            elevator_id=elevator_id, request_number=request_number, lang=lang,
        )
    except (SQLAlchemyError, TelegramAPIError, RuntimeError, ValueError) as exc:
        logger.warning("Подсказка о лифте по заявке %s не отправлена: %s",
                       request_number, type(exc).__name__)


@router.callback_query(F.data.startswith("reconfirm_completed_"))
async def handle_manager_reconfirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер повторно подтверждает выполнение возвратной заявки"""
    try:
        lang = language

        logger.info(f"Повторное подтверждение возвратной заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("reconfirm_completed_", "")

        # PR2a-2: под каноном (модель A) у статуса «Возвращена» нет ребра
        # обратно в «Исполнено». Кнопка reconfirm = MANAGER_FORCE_ACCEPT
        # (продуктовое решение 2026-06-10): менеджер отклоняет возврат →
        # заявка принимается терминально (Возвращена→Принято), повторной
        # приёмки заявителем больше нет.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_FORCE_ACCEPT, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_FORCE_ACCEPT (reconfirm) отклонён для {request_number}: {e}")
            await _answer_already_handled(callback, request_number, lang)
            return

        # Best-effort post-commit (PR0 Р7): уведомления + правка сообщения.
        request = AdminHandlerService(db).get_request_by_number(request_number)

        # Адресно — по матрице интентов (не бросает); в канал — хелпером.
        await dispatch_notify_intents_sync(
            db, request_number, outcome.post_commit_intents, bot=callback.bot)
        await notify_channel_status_changed(
            callback.bot, request, outcome.old_status, outcome.public_status)

        # Дополнительное уведомление заявителю: возврат рассмотрен, заявка принята
        applicant = request.user if request else None
        if applicant and applicant.telegram_id:
            try:
                bot = callback.bot

                notification_text = get_text("admin.handlers.notify_applicant_reconfirmed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о принятии возвратной заявки {request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_reconfirmed", language=lang).format(request_number=request_number)
        )

        logger.info(f"Возврат по заявке {request_number} отклонён, принято менеджером {user.id} (canon force-accept)")

    except Exception as e:
        logger.error(f"Ошибка повторного подтверждения заявки: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("return_to_work_"))
async def handle_manager_return_to_work(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер возвращает заявку в работу — шаг 1: спрашиваем причину.

    Сам переход исполняет `handle_return_to_work_reason`: возврат без причины
    бесполезен исполнителю, поэтому она обязательна (ядро отклонит пустой
    payload). Оживляет уже объявленное состояние `awaiting_return_to_work_reason`.
    """
    try:
        lang = language
        logger.info(f"Возврат заявки в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_change_status", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("return_to_work_", "")

        await callback.message.edit_text(
            get_text("admin.handlers.return_to_work_prompt", language=lang).format(
                request_number=request_number),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=get_text("admin.handlers.btn_cancel", language=lang),
                    # СВОЙ callback, а не общий `view_`: тот не снимает FSM, и
                    # состояние «жду причину» пережило бы отмену. Тогда любое
                    # следующее сообщение менеджера — заметка, ответ в другом
                    # диалоге — было бы съедено как причина и молча вернуло бы
                    # заявку в работу.
                    callback_data=f"rtw_cancel_{request_number}")
            ]]),
        )

        await state.update_data(return_to_work_number=request_number)
        await remember_prompt(callback, state)
        await state.set_state(ManagerAcceptanceStates.awaiting_return_to_work_reason)

        logger.info(f"Запрошена причина возврата в работу по заявке {request_number}")

    except Exception as e:
        logger.error(f"Ошибка запроса причины возврата в работу: {e}")
        await callback.answer(get_text("admin.handlers.error_changing_status", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("rtw_cancel_"))
async def handle_return_to_work_cancel(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена сбора причины: снимаем состояние, иначе следующее сообщение
    менеджера будет принято за причину и вернёт заявку в работу."""
    await state.clear()
    request_number = callback.data.replace("rtw_cancel_", "")
    await callback.message.edit_text(
        get_text("admin.handlers.return_to_work_cancelled", language=language).format(
            request_number=request_number)
    )


@router.message(ManagerAcceptanceStates.awaiting_return_to_work_reason)
async def handle_return_to_work_reason(message: Message, state: FSMContext, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Шаг 2: причина получена — исполняем канонический переход."""
    lang = language
    try:
        if not has_admin_access(roles=roles, user=user):
            await message.answer(get_text("admin.handlers.no_access_change_status", language=lang))
            await state.clear()
            return

        reason = (message.text or "").strip()
        if not reason:
            # Не отправляем пустое в движок — он всё равно отклонит, а менеджер
            # получил бы невнятную ошибку вместо понятной просьбы.
            await message.answer(get_text("admin.handlers.return_to_work_reason_empty", language=lang))
            return

        data = await state.get_data()
        request_number = data.get("return_to_work_number")
        if not request_number:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return

        # Канонический переход (PR2a-2): Выполнена/Возвращена → В работе.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(f"rtw:{request_number}:{message.message_id}",
                              Action.MANAGER_RETURN_TO_WORK, {"reason": reason}),
            )
        except RequestNotFound:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_RETURN_TO_WORK отклонён для {request_number}: {e}")
            # Канон отказал — заявку уже обработали: пишем это в ту же подсказку.
            stale = await already_handled_text(request_number, lang)
            if not await close_prompt(message, state, stale):
                await message.answer(stale)
            await state.clear()
            return

        # Best-effort post-commit (PR0 Р7): уведомление + подтверждение менеджеру.
        request = AdminHandlerService(db).get_request_by_number(request_number)
        await dispatch_notify_intents_sync(
            db, request_number, outcome.post_commit_intents, bot=message.bot)
        await notify_channel_status_changed(
            message.bot, request, outcome.old_status, outcome.public_status)

        done = get_text("admin.handlers.request_returned_to_work", language=lang).format(
            request_number=request_number)
        # Итог — в исходное сообщение (бывшую карточку), новым — только если не вышло.
        if not await close_prompt(message, state, done):
            await message.answer(done)
        await state.clear()

        logger.info(f"Заявка {request_number} возвращена в работу менеджером {user.id} (canon)")

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await message.answer(get_text("admin.handlers.error_changing_status", language=lang))
        await state.clear()


@router.callback_query(F.data.startswith("mreq_page_"))
async def handle_manager_request_pagination(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка пагинации списков заявок для менеджеров"""
    try:
        lang = language
        logger.info(f"Обработка пагинации заявок менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return

        # `mreq_page_<kind>_<n>`; старые сообщения шлют `mreq_page_<n>` — это активные.
        page_data = callback.data.replace("mreq_page_", "")
        if page_data == "curr":
            await callback.answer(get_text("admin.handlers.current_page", language=lang))
            return
        kind, _, page_str = page_data.rpartition("_")
        kind = kind or "active"
        if kind not in _MANAGER_LISTS or not page_str.isdigit():
            await callback.answer(get_text("admin.handlers.page_not_found", language=lang), show_alert=True)
            return
        current_page = int(page_str)

        text, markup = build_manager_list(AdminHandlerService(db), kind, current_page, lang)
        await edit_quiet(callback, text, markup)
        await callback.answer()
        logger.info(f"Показана страница {current_page} заявок менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки пагинации заявок менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


