"""Исполнитель: групповой пул, взятие, закуп/выполнение заявки (ExecutorRequestStates)."""

from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
from uk_management_bot.services.request_handler_service import RequestHandlerService

from uk_management_bot.keyboards.base import get_user_contextual_keyboard
import logging

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text, get_user_language
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix

from ._router import router

from .shared import (
    _db_scope,
    GROUP_POOL_TEXTS,
)

logger = logging.getLogger(__name__)


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

# NOTE: assign_duty_* is handled by handlers/admin.py:handle_assign_duty_executor_admin,
# which commits the group assignment and notifies executors on an active shift.
# A duplicate handler here previously shadowed it (requests_router is registered
# before admin_router) and silently dropped the assignment — see test_bug_duty_assign_routing.


# NOTE: assign_specific_* and assign_executor_* are handled by handlers/admin.py
# (handle_assign_specific_executor_admin / handle_final_executor_assignment_admin), which
# route through AssignmentService — creating a RequestAssignment row, cancelling stale
# assignments, and writing an audit log. Duplicate copies lived here and shadowed them
# (requests_router precedes admin_router); the old copy set request.executor_id directly
# with assignment_type="manual" and skipped the assignment record/audit. See
# test_bug_duty_assign_routing.


# `back_to_assignment_type_*` обрабатывается в handlers/admin.py::
# handle_back_to_assignment_type_admin (функционально идентичная копия). Дубликат
# здесь затенял её (requests_router раньше admin_router). Удалён —
# см. test_bug_duty_assign_routing::test_back_to_assignment_type_owned_by_admin.


# ============================
# ОБРАБОТЧИКИ ИСПОЛНИТЕЛЯ
# ============================

class ExecutorRequestStates(StatesGroup):
    """Состояния для работы исполнителя с заявками"""
    waiting_purchase_comment = State()  # Ожидание комментария для закупа
    waiting_completion_comment = State()  # Ожидание комментария для завершения
    waiting_completion_media = State()  # Ожидание медиа для завершения


@router.callback_query(F.data.startswith("executor_view_media_"))
async def executor_view_media(callback: CallbackQuery):
    """Просмотр медиа-файлов заявки исполнителем"""
    try:
        request_number = callback.data.replace("executor_view_media_", "")
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            request = service.get_request_by_number(request_number)

            if not request:
                await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
                return

            request_media_files = request.media_files

        # Отправляем медиа-файлы
        from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
        import json

        media_group = []

        if request_media_files:
            try:
                media_files = json.loads(request_media_files) if isinstance(request_media_files, str) else request_media_files
                if media_files:
                    for media in media_files:
                        file_id = media.get('file_id') if isinstance(media, dict) else media
                        media_type = media.get('type', 'photo') if isinstance(media, dict) else 'photo'

                        if media_type == 'photo':
                            media_group.append(InputMediaPhoto(media=file_id))
                        elif media_type == 'video':
                            media_group.append(InputMediaVideo(media=file_id))
                        elif media_type == 'document':
                            media_group.append(InputMediaDocument(media=file_id))
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Ошибка парсинга media_files: {e}")

        if media_group:
            await callback.message.answer_media_group(media=media_group)
            await callback.answer(get_text("requests.media_files_sent", language=lang))
        else:
            await callback.answer(get_text("requests.no_media_files", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка просмотра медиа исполнителем: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)


def _run_executor_command(request_number: str, user_id, action, payload: dict,
                          command_id: str):
    """PR2a-5: исполнительский переход через единый layer (canonical-write).

    run_command сам грузит под FOR UPDATE, авторизует (assigned + активная
    смена), пишет patch+audit+outbox в одной tx. Возвращает (outcome, error_key):
    error_key=None при успехе, иначе ключ локали для ответа пользователю.
    """
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.workflow_runner import (
        run_command_sync, RequestNotFound)
    from uk_management_bot.utils.request_workflow import (
        ActionCommand, PrincipalRef,
        NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
        WorkflowError)
    try:
        outcome = run_command_sync(
            SessionLocal, request_number,
            PrincipalRef(kind="user", user_id=user_id, source="telegram"),
            ActionCommand(command_id, action, payload),
        )
        return outcome, None
    except RequestNotFound:
        return None, "requests.request_not_found"
    except NotAuthorized:
        return None, "requests.executor_not_authorized"
    except (InvalidTransition, RepeatRejected, RepeatConflict):
        return None, "requests.executor_status_conflict"
    except WorkflowError:
        return None, "common.error"


def _build_group_pool_view(db_session: Session, user: User, lang: str):
    """FEAT-группы: построить (text, keyboard|None) пула «свободных» group-заявок
    с кнопкой «🙋 Взять #N» по каждой. Пустой пул → текст без клавиатуры."""
    from uk_management_bot.keyboards.requests import (
        resolve_category_key, get_category_display)
    from uk_management_bot.utils.address_helpers import localize_address

    pool = RequestHandlerService(db_session).list_group_pool(user)
    title = get_text("requests.group_pool_title", language=lang) or "🆓 Свободные заявки"
    if not pool:
        empty = get_text("requests.group_pool_empty", language=lang) or "Свободных заявок нет"
        return f"{title}\n\n{empty}", None

    claim_text = get_text("requests.executor_claim_button", language=lang) or "🙋 Взять в работу"
    address_label = get_text("requests.address_label", language=lang) or "Адрес"
    lines = [title, ""]
    rows: list = []
    for i, r in enumerate(pool, 1):
        category_display = get_category_display(resolve_category_key(r.category), language=lang)
        lines.append(f"{i}. 🔧 #{r.request_number} — {category_display}")
        lines.append(f"   {address_label} {localize_address(r.address, lang)}")
        lines.append("")
        rows.append([InlineKeyboardButton(
            text=f"{claim_text} #{r.request_number}",
            callback_data=f"claim_request_{r.request_number}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_group_pool(message: Message, db_session: Session,
                             user: User, lang: str) -> None:
    """edit-вариант (перерисовка после взятия / открытия из inline)."""
    text, kb = _build_group_pool_view(db_session, user, lang)
    try:
        await message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.message(F.text.in_(GROUP_POOL_TEXTS))
async def show_group_pool_message(message: Message, state: FSMContext):
    """FEAT-группы: реплай-кнопка «🆓 Свободные заявки» (исполнитель) → пул."""
    try:
        with _db_scope(None) as db_session:
            lang = get_user_language(message.from_user.id, db_session)
            user = RequestHandlerService(db_session).get_user_by_telegram_id(
                message.from_user.id)
            if not user:
                await message.answer(get_text("common.user_not_found", language=lang))
                return
            text, kb = _build_group_pool_view(db_session, user, lang)
            await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Ошибка показа пула (реплай): {e}")
        await message.answer(get_text("common.error", language="ru"))


async def _notify_group_pool_claimed(db_session: Session, request_number: str,
                                     claimer: User) -> None:
    """FEAT-группы (best-effort, вне tx): уведомить остальных дежурных группы,
    что заявку #N взял {claimer}. Таргет — on-shift исполнители той же
    специализации (group_specialization сохранён в назначении как история)."""
    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        from uk_management_bot.utils.auth_helpers import get_user_roles
        from uk_management_bot.utils.constants import ROLE_EXECUTOR
        from uk_management_bot.utils.shifts import is_on_shift_now_sync
        from uk_management_bot.utils.specializations import parse_specializations

        service = RequestHandlerService(db_session)
        assignment = service.get_active_assignment(request_number)
        spec = assignment.group_specialization if assignment else None
        if not spec:
            return
        bot = _get_shared_bot()
        if bot is None:
            return
        claimer_name = claimer.first_name or str(claimer.id)
        for ex in service.list_approved_users():
            if ex.id == claimer.id or not ex.telegram_id:
                continue
            if ROLE_EXECUTOR not in get_user_roles(ex):
                continue
            if spec not in parse_specializations(ex):
                continue
            if not is_on_shift_now_sync(db_session, ex.id):
                continue
            text = get_text("requests.claimed_by_other_notify",
                            language=(ex.language or "ru")).format(
                request_number=request_number, executor=claimer_name)
            try:
                await bot.send_message(chat_id=ex.telegram_id, text=text)
            except Exception as e:
                logger.debug(f"claim-notify исполнителю {ex.id} пропущено: {e}")
    except Exception as e:
        logger.warning(f"claim-notify для {request_number} не выполнен: {e}")


@router.callback_query(F.data == "group_pool")
async def show_group_pool(callback: CallbackQuery, state: FSMContext):
    """FEAT-группы: открыть пул «свободных» group-заявок (только дежурным)."""
    try:
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)
            user = RequestHandlerService(db_session).get_user_by_telegram_id(
                callback.from_user.id)
            if not user:
                await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
                return
            await _render_group_pool(callback.message, db_session, user, lang)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка показа пула свободных заявок: {e}")
        await callback.answer(get_text("common.error", language="ru"), show_alert=True)


@router.callback_query(F.data.startswith("claim_request_"))
async def claim_group_request(callback: CallbackQuery, state: FSMContext):
    """FEAT-группы: исполнитель «берёт» group-заявку из пула (EXECUTOR_CLAIM).

    Успех → группа конвертируется в individual на взявшего; заявка уходит из
    пула, у взявшего появляются рабочие действия. NotAuthorized → «уже взято».
    """
    from uk_management_bot.utils.request_workflow import Action
    try:
        request_number = callback.data.replace("claim_request_", "")
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)
            user = RequestHandlerService(db_session).get_user_by_telegram_id(
                callback.from_user.id)
            if not user:
                await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
                return
            _outcome, error_key = _run_executor_command(
                request_number, user.id, Action.EXECUTOR_CLAIM, {}, callback.id)
            if error_key is not None:
                # В контексте взятия NotAuthorized/конфликт = заявку уже взяли.
                if error_key in ("requests.executor_not_authorized",
                                 "requests.executor_status_conflict"):
                    msg = get_text("requests.request_already_claimed", language=lang) \
                        or "Заявку уже взяли"
                else:
                    msg = get_text(error_key, language=lang)
                await callback.answer(msg, show_alert=True)
                # пул мог измениться — перерисовать
                await _render_group_pool(callback.message, db_session, user, lang)
                return
            await callback.answer(
                get_text("requests.request_claimed_success", language=lang)
                or "Вы взяли заявку в работу", show_alert=True)
            await _notify_group_pool_claimed(db_session, request_number, user)
            await _render_group_pool(callback.message, db_session, user, lang)
    except Exception as e:
        logger.error(f"Ошибка взятия заявки из пула: {e}")
        await callback.answer(get_text("common.error", language="ru"), show_alert=True)


@router.callback_query(F.data.startswith("executor_purchase_"))
async def executor_request_purchase(callback: CallbackQuery, state: FSMContext):
    """Исполнитель переводит заявку в 'Закуп'"""
    try:
        request_number = callback.data.replace("executor_purchase_", "")
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        await state.update_data(executor_request_number=request_number)
        await state.set_state(ExecutorRequestStates.waiting_purchase_comment)

        await callback.message.edit_text(
            get_text("requests.executor_purchase_prompt", language=lang).format(request_number=request_number),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала процесса закупа: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)


@router.message(ExecutorRequestStates.waiting_purchase_comment)
async def executor_process_purchase_comment(message: Message, state: FSMContext):
    """Обработка комментария для закупа"""
    try:
        data = await state.get_data()
        request_number = data.get("executor_request_number")

        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(message.from_user.id, db_session)

            request = service.get_request_by_number(request_number)

            if not request:
                await message.answer(get_text("requests.request_not_found", language=lang))
                await state.clear()
                return

            # Канонический переход (PR2a-5): EXECUTOR_PURCHASE (В работе→Закуп)
            # через единый layer. Комментарий исполнителя → requested_materials
            # (канон-поле). Активную смену + назначение проверяет run_command.
            from uk_management_bot.utils.request_workflow import Action
            actor = service.get_user_by_telegram_id(message.from_user.id)
            outcome, err = _run_executor_command(
                request_number, actor.id if actor else None,
                Action.EXECUTOR_PURCHASE, {"requested_materials": message.text},
                command_id=f"exec-purchase-{request_number}-{message.message_id}",
            )
            if err:
                await message.answer(get_text(err, language=lang))
                await state.clear()
                return

            # Best-effort post-commit: уведомление + ответ. run_command коммитит в
            # отдельной сессии → expire_all сбрасывает identity-map middleware-сессии,
            # иначе повторный query вернёт устаревший объект (не свежий).
            service.expire_all()
            request = service.get_request_by_number(request_number)
            from uk_management_bot.services.notification_service import async_notify_request_status_changed
            try:
                bot = message.bot
                await async_notify_request_status_changed(bot, db_session, request, outcome.old_status, outcome.public_status)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")

        await message.answer(
            get_text("requests.purchase_comment_saved", language=lang).format(request_number=request_number),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обработки комментария закупа: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("common.error", language=lang))
        await state.clear()


@router.callback_query(F.data.startswith("executor_complete_"))
async def executor_complete_request(callback: CallbackQuery, state: FSMContext):
    """Исполнитель переводит заявку в 'Выполнено'"""
    try:
        request_number = callback.data.replace("executor_complete_", "")
        with _db_scope(None) as db_session:
            lang = get_user_language(callback.from_user.id, db_session)

        await state.update_data(executor_request_number=request_number, completion_media=[])
        await state.set_state(ExecutorRequestStates.waiting_completion_comment)

        await callback.message.edit_text(
            get_text("requests.executor_complete_prompt", language=lang).format(request_number=request_number),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала завершения заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)


@router.message(ExecutorRequestStates.waiting_completion_comment)
async def executor_process_completion_comment(message: Message, state: FSMContext):
    """Обработка комментария для завершения"""
    try:
        data = await state.get_data()
        request_number = data.get("executor_request_number")

        with _db_scope(None) as db_session:
            lang = get_user_language(message.from_user.id, db_session)

        await state.update_data(completion_comment=message.text)
        await state.set_state(ExecutorRequestStates.waiting_completion_media)

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("requests.finish_without_media", language=lang), callback_data=f"executor_finish_completion_{request_number}")],
            [InlineKeyboardButton(text=get_text("common.cancel", language=lang), callback_data=f"view_request_{request_number}")]
        ])

        await message.answer(
            get_text("requests.send_completion_media_prompt", language=lang),
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка обработки комментария завершения: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("common.error", language=lang))
        await state.clear()


@router.message(ExecutorRequestStates.waiting_completion_media, F.photo | F.video | F.document)
async def executor_collect_completion_media(message: Message, state: FSMContext):
    """Сбор медиа-файлов для завершения заявки"""
    try:
        data = await state.get_data()
        completion_media = data.get("completion_media", [])
        request_number = data.get("executor_request_number")

        with _db_scope(None) as db_session:
            lang = get_user_language(message.from_user.id, db_session)

        # Добавляем файл в список
        if message.photo:
            completion_media.append({"type": "photo", "file_id": message.photo[-1].file_id})
        elif message.video:
            completion_media.append({"type": "video", "file_id": message.video.file_id})
        elif message.document:
            completion_media.append({"type": "document", "file_id": message.document.file_id})

        await state.update_data(completion_media=completion_media)

        # Обновляем клавиатуру с счетчиком
        finish_button_text = get_text("requests.finish_with_files", language=lang).format(count=len(completion_media))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=finish_button_text, callback_data=f"executor_finish_completion_{request_number}")],
            [InlineKeyboardButton(text=get_text("common.cancel", language=lang), callback_data=f"view_request_{request_number}")]
        ])

        await message.answer(
            get_text("requests.file_added_send_more", language=lang).format(count=len(completion_media)),
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка сбора медиа для завершения: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("common.error", language=lang))


@router.callback_query(F.data.startswith("executor_finish_completion_"))
async def executor_finish_completion(callback: CallbackQuery, state: FSMContext):
    """Финализация завершения заявки"""
    try:
        request_number = callback.data.replace("executor_finish_completion_", "")
        data = await state.get_data()
        completion_comment = data.get("completion_comment", "")
        completion_media = data.get("completion_media", [])

        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            request = service.get_request_by_number(request_number)

            if not request:
                await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
                await state.clear()
                return

            # Загружаем медиа-файлы в Media Service (если есть)
            media_service_files = []
            if completion_media:
                from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
                bot = callback.bot

                # Получаем user_id для uploaded_by
                user = service.get_user_by_telegram_id(callback.from_user.id)
                uploaded_by = user.id if user else None

                logger.info(f"Загрузка {len(completion_media)} файлов в Media Service для заявки {request_number}")

                for idx, media_item in enumerate(completion_media, 1):
                    file_id = media_item.get("file_id")
                    file_type = media_item.get("type", "photo")

                    # Определяем report_type на основе типа файла
                    if file_type == "video":
                        report_type = "completion_video"
                    elif file_type == "document":
                        report_type = "completion_document"
                    else:
                        report_type = "completion_photo"

                    try:
                        result = await upload_report_file_to_media_service(
                            bot=bot,
                            file_id=file_id,
                            request_number=request_number,
                            report_type=report_type,
                            description=f"Report #{idx}",
                            uploaded_by=uploaded_by
                        )

                        if result:
                            media_service_files.append({
                                "media_id": result["media_file"]["id"],
                                "file_url": result["media_file"]["file_url"],
                                "type": file_type
                            })
                            logger.info(f"Файл #{idx} загружен в Media Service: media_id={result['media_file']['id']}")
                        else:
                            logger.warning(f"Не удалось загрузить файл #{idx} в Media Service")

                    except Exception as e:
                        logger.error(f"Ошибка загрузки файла #{idx} в Media Service: {e}")

            # Канонический переход (PR2a-5): EXECUTOR_COMPLETE (В работе→Выполнена)
            # через единый layer. Медиа уже загружены в Media Service ВЫШЕ (сетевой
            # I/O — вне транзакции). Отчёт → completion_report, файлы →
            # completion_media (list; ридеры принимают и list, и json-строку).
            from uk_management_bot.utils.request_workflow import Action
            actor = service.get_user_by_telegram_id(callback.from_user.id)
            media_payload = media_service_files if media_service_files else completion_media
            outcome, err = _run_executor_command(
                request_number, actor.id if actor else None,
                Action.EXECUTOR_COMPLETE,
                {"completion_report": completion_comment or "",
                 "completion_media": media_payload or []},
                command_id=f"exec-complete-{request_number}-{callback.id}",
            )
            if err:
                await callback.answer(get_text(err, language=lang), show_alert=True)
                await state.clear()
                return

            # Best-effort post-commit: уведомление. expire_all сбрасывает identity-map
            # middleware-сессии (run_command коммитит в отдельной) → query вернёт свежий объект.
            service.expire_all()
            request = service.get_request_by_number(request_number)
            from uk_management_bot.services.notification_service import async_notify_request_status_changed
            try:
                await async_notify_request_status_changed(callback.bot, db_session, request, outcome.old_status, outcome.public_status)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")

            # Формируем сообщение с результатом
            message_text = get_text("requests.request_completed_title", language=lang).format(request_number=request_number)
            message_text += get_text("requests.comment_label", language=lang).format(comment=completion_comment)
            if media_service_files:
                message_text += get_text("requests.files_uploaded_to_media_service", language=lang).format(count=len(media_service_files))
            elif completion_media:
                message_text += get_text("requests.files_saved_locally", language=lang).format(count=len(completion_media))

            await callback.message.edit_text(message_text, parse_mode="HTML")

            await state.clear()
            await callback.answer(get_text("requests.request_completed_short", language=lang))

    except Exception as e:
        logger.error(f"Ошибка финализации завершения: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
        await state.clear()


@router.callback_query(F.data.startswith("executor_work_"))
async def executor_return_to_work(callback: CallbackQuery):
    """Возврат заявки в работу из статуса Закуп/Уточнение"""
    try:
        request_number = callback.data.replace("executor_work_", "")
        with _db_scope(None) as db_session:
            service = RequestHandlerService(db_session)
            lang = get_user_language(callback.from_user.id, db_session)

            # Канонический переход (PR2a-5): EXECUTOR_RESUME (Закуп/Уточнение→
            # В работе) через единый layer. Исполнителю разрешён self-resume
            # (продуктовое решение 2026-06-10); активную смену+назначение проверяет
            # run_command.
            from uk_management_bot.utils.request_workflow import Action
            actor = service.get_user_by_telegram_id(callback.from_user.id)
            outcome, err = _run_executor_command(
                request_number, actor.id if actor else None,
                Action.EXECUTOR_RESUME, {},
                command_id=f"exec-resume-{request_number}-{callback.id}",
            )
            if err:
                await callback.answer(get_text(err, language=lang), show_alert=True)
                return

            # Best-effort post-commit: уведомление. expire_all сбрасывает identity-map
            # middleware-сессии (run_command коммитит в отдельной) → query вернёт свежий объект.
            service.expire_all()
            request = service.get_request_by_number(request_number)
            from uk_management_bot.services.notification_service import async_notify_request_status_changed
            try:
                bot = callback.bot
                await async_notify_request_status_changed(bot, db_session, request, outcome.old_status, outcome.public_status)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")

            await callback.message.edit_text(
                get_text("requests.request_returned_to_work", language=lang).format(request_number=request_number),
                parse_mode="HTML"
            )
            await callback.answer(get_text("requests.request_in_work", language=lang))

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
