"""
Обработчики для управления отчетами о выполнении заявок
Обеспечивает функциональность просмотра и принятия отчетов

AUD3-07/AUD5-ARCH-1: DB-фаза хендлеров — цельный sync unit-of-work в
worker-потоке (``run_db``), наружу DTO/скаляры. Канонический переход
``run_command_sync`` (своя сессия из SessionLocal) уходит в поток целиком
через ``asyncio.to_thread``. Сеть — в async-слое, вне сессии.
"""

import asyncio
import html
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from dataclasses import dataclass
from typing import Optional

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.states.request_reports import RequestReportStates
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.services.request_access import has_request_access_sync
from uk_management_bot.keyboards.request_reports import (
    get_report_confirmation_keyboard,
    get_report_actions_keyboard
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display
from uk_management_bot.utils.address_helpers import localize_address
from uk_management_bot.keyboards.requests import (
    get_category_display,
    resolve_category_key,
)
from uk_management_bot.utils.workflow_predicates import is_awaiting_applicant
from uk_management_bot.utils.constants import (
    ROLE_APPLICANT,
)

router = Router()
logger = logging.getLogger(__name__)


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки.
# ==========================================================================

@dataclass(frozen=True)
class _ReportView:
    """Готовый экран отчёта: текст собран в юните, клавиатура — снаружи."""
    request_number: str
    status: str
    report_text: str


@dataclass(frozen=True)
class _RequestBrief:
    """Поля заявки, нужные экранам «принять» / «на доработку»."""
    status: str
    category: str
    address: Optional[str]


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================

def _load_report_view(db, request_number: str, telegram_id: int, lang: str) -> tuple:
    """-> ('request_not_found'|'user_not_found'|'no_access'|'no_report', None)
       | ('ok', _ReportView).

    Текст отчёта рендерится здесь же (B3): format_report_for_display читает
    ORM-заявку и lazy-связь ``comment.user`` — вне сессии их не существует.
    """
    # Проверяем существование заявки
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    # Пользователь ищется по telegram_id, а НЕ по id: `callback.from_user.id`
    # это Telegram-идентификатор, а `users.id` — обычный serial. Прежний
    # `User.id == callback.from_user.id` не находил никого, из-за чего
    # хендлер всегда отвечал «пользователь не найден» и до самого отчёта
    # дело не доходило (тестами это место не покрыто).
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return ("user_not_found", None)

    # Права — канон `utils/request_access` (П5). Здесь была копия правил, в
    # которой роль проверялась подстрокой по JSON-тексту `user.roles`
    # ('manager' in '["manager"]'), не учитывались назначения через
    # RequestAssignment, а `request.user_id` сравнивался с Telegram-id.
    has_access = has_request_access_sync(db, user, request)

    if not has_access:
        return ("no_access", None)

    # Проверяем, есть ли отчет
    if not request.completion_report:
        return ("no_report", None)

    # Получаем комментарии с отчетами
    comment_service = CommentService(db)
    report_comments = comment_service.get_comments_by_type(request.request_number, "report")

    # Формируем текст отчета
    report_text = format_report_for_display(request, report_comments, lang)

    return (
        "ok",
        _ReportView(
            request_number=request.request_number,
            status=request.status,
            report_text=report_text,
        ),
    )


def _load_applicant_action_context(db, request_number: str, telegram_id: int) -> tuple:
    """Общая db-фаза кнопок заявителя «принять» / «на доработку».

    -> ('no_role'|'request_not_found'|'not_owner'|'not_awaiting', None)
       | ('ok', _RequestBrief).
    """
    # BUG-153 п.4: единый резолв telegram_id -> users.id. Раньше в
    # check_user_role уходил Telegram-id (фильтр по serial-ключу), а владение
    # сверялось request.user_id == telegram_id — обе кнопки заявителя всегда
    # отвечали «нет доступа». Дальше мутации идут КАНОНОМ (run_command
    # авторизует владельца сам), так что оживление пути безопасно.
    from uk_management_bot.utils.auth_helpers import get_user_roles
    actor = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not actor or ROLE_APPLICANT not in set(get_user_roles(actor) or []):
        return ("no_role", None)

    # Проверяем существование заявки
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    # Владение — по внутреннему users.id
    if request.user_id != actor.id:
        return ("not_owner", None)

    # PR2a-6: заявка ожидает решения заявителя (Исполнено, не возвращена) —
    # канон-предикат вместо сырого status==Исполнено (возвращённые ждут
    # менеджера и в отчёт/доработку заявителем не идут).
    if not is_awaiting_applicant(request):
        return ("not_awaiting", None)

    return (
        "ok",
        _RequestBrief(
            status=request.status,
            category=request.category,
            address=request.address,
        ),
    )


def _load_revision_actor(db, request_number: str, telegram_id: int) -> tuple:
    """-> ('request_not_found'|'actor_not_found', None) | ('ok', actor_id)."""
    # Получаем текущую заявку
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    actor = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not actor:
        return ("actor_not_found", None)

    return ("ok", actor.id)


def _add_revision_comment(db, request_number: str, telegram_id: int, revision_reason: str) -> list:
    """Добавляем комментарий о доработке (пишет и коммитит CommentService).

    -> list[CommentNotice] для отправки async-слоем (BUG-174: из worker-потока
    run_db слать нечем, доставку делает хендлер).

    BUG-153 п.5: вызов шёл с чужим keyword `request_id=` при сигнатуре
    ``add_clarification_comment(request_number, user_id, clarification)`` и с
    Telegram-id в `user_id` (``add_comment`` ищет ``User.id``). Первый дефект
    ронял вызов TypeError ещё до второго, поэтому причина доработки не
    сохранялась никогда: переход APPLICANT_RETURN к этому моменту уже
    закоммичен, и заявитель видел «ошибка» при сменившемся статусе.

    Текст комментария — через локаль на языке актора (BUG-153 п.2).
    """
    actor = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not actor:
        logger.warning(
            f"Комментарий о доработке не сохранён: пользователь telegram_id={telegram_id} не найден"
        )
        return []

    comment_service = CommentService(db)

    _, notices = comment_service.add_clarification_comment(
        request_number=request_number,
        user_id=actor.id,
        clarification=get_text(
            "request_reports.handlers.revision_comment",
            language=actor.language or "ru",
        ).format(reason=revision_reason)
    )
    return notices


@router.callback_query(F.data.startswith("view_report_"))
async def handle_view_report(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Просмотр отчета о выполнении заявки"""
    try:
        # Получаем номер заявки
        request_number = callback.data.split("_")[-1]

        lang = language
        verdict, view = await run_db(
            lambda s: _load_report_view(s, request_number, callback.from_user.id, lang), db=_db
        )

        if verdict == "request_not_found":
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.request_not_found", language=language), show_alert=True)
            return

        if verdict == "user_not_found":
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.user_not_found", language=language), show_alert=True)
            return

        if verdict == "no_access":
            await callback.answer(get_text("request_reports.handlers.no_access_view_report", language=language), show_alert=True)
            return

        if verdict == "no_report":
            await callback.answer(get_text("request_reports.handlers.no_report_yet", language=language), show_alert=True)
            return

        # Показываем отчет
        keyboard = get_report_actions_keyboard(view.request_number, view.status, lang)

        await callback.message.edit_text(
            view.report_text,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра отчета: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("approve_request_"))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Принятие заявки заявителем"""
    try:
        request_number = callback.data.split("_")[-1]

        verdict, brief = await run_db(
            lambda s: _load_applicant_action_context(s, request_number, callback.from_user.id), db=_db
        )

        if verdict == "no_role":
            await callback.answer(get_text("request_reports.handlers.no_access_approve", language=language), show_alert=True)
            return

        if verdict == "request_not_found":
            await callback.answer(get_text("request_reports.handlers.request_not_found", language=language), show_alert=True)
            return

        if verdict == "not_owner":
            await callback.answer(get_text("request_reports.handlers.only_own_requests", language=language), show_alert=True)
            return

        if verdict == "not_awaiting":
            await callback.answer(get_text("request_reports.handlers.only_completed_requests", language=language), show_alert=True)
            return

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            current_status=brief.status
        )

        # Показываем подтверждение принятия
        lang = language
        keyboard = get_report_confirmation_keyboard(lang)

        confirmation_text = get_text("reports.approval_confirmation", language=lang).format(
            request_id=request_number,
            category=brief.category,
            address=brief.address
        )

        await callback.message.edit_text(
            confirmation_text,
            reply_markup=keyboard
        )

        # Переходим в состояние подтверждения
        await state.set_state(RequestReportStates.waiting_for_approval_confirmation)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка принятия заявки: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "confirm_approval")
async def handle_approval_confirmation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Подтверждение принятия заявки"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await callback.answer(get_text("request_reports.handlers.request_data_not_found", language=language), show_alert=True)
            return

        # SSOT-кластер #1, PR2d: приёмка заявителем = канонический rated-accept
        # (APPLICANT_ACCEPT с оценкой). Прежний прямой перевод в «Принято» без
        # рейтинга через update_request_status снят. Редирект на канон:
        # показываем клавиатуру оценки 1–5★, приёмку выполнит
        # request_acceptance.save_rating → run_command(APPLICANT_ACCEPT).
        from uk_management_bot.keyboards.admin import get_rating_keyboard
        await state.clear()
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.rate_request", language=language),
            reply_markup=get_rating_keyboard(request_number),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения принятия: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_approval")
async def handle_approval_cancellation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена принятия заявки"""
    try:
        # Очищаем состояние
        await state.clear()

        lang = language
        await callback.message.edit_text(get_text("request_reports.handlers.approval_cancelled", language=lang))
        await callback.answer(get_text("request_reports.handlers.approval_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены принятия: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("request_revision_"))
async def handle_request_revision(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Запрос доработки заявки"""
    try:
        request_number = callback.data.split("_")[-1]

        verdict, brief = await run_db(
            lambda s: _load_applicant_action_context(s, request_number, callback.from_user.id), db=_db
        )

        if verdict == "no_role":
            await callback.answer(get_text("request_reports.handlers.no_access_revision", language=language), show_alert=True)
            return

        if verdict == "request_not_found":
            await callback.answer(get_text("request_reports.handlers.request_not_found", language=language), show_alert=True)
            return

        if verdict == "not_owner":
            await callback.answer(get_text("request_reports.handlers.only_own_revision", language=language), show_alert=True)
            return

        if verdict == "not_awaiting":
            await callback.answer(get_text("request_reports.handlers.only_completed_revision", language=language), show_alert=True)
            return

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="revision"
        )

        # Запрашиваем причину доработки
        lang = language
        await callback.message.edit_text(
            get_text("reports.enter_revision_reason", language=lang)
        )

        # Переходим в состояние ввода причины
        await state.set_state(RequestReportStates.waiting_for_revision_reason)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка запроса доработки: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestReportStates.waiting_for_revision_reason)
async def handle_revision_reason_input(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка ввода причины доработки"""
    try:
        # Получаем причину доработки
        revision_reason = message.text.strip()

        if not revision_reason:
            await message.answer(get_text("request_reports.handlers.enter_revision_reason_prompt", language=language))
            return

        if len(revision_reason) < 10:
            await message.answer(get_text("request_reports.handlers.revision_reason_too_short", language=language))
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        verdict, actor_id = await run_db(
            lambda s: _load_revision_actor(s, request_number, message.from_user.id), db=_db
        )

        # Обе ветки исторически отвечали одним и тем же текстом «заявка не
        # найдена» — сохранено 1:1.
        if verdict in ("request_not_found", "actor_not_found"):
            await message.answer(get_text("request_reports.handlers.request_not_found", language=language))
            return

        # SSOT-кластер #1, PR2d: доработка заявителем = канонический возврат
        # (APPLICANT_RETURN, Исполнено→Возвращена; дальше разбирает менеджер).
        # Прежний прямой перевод в «В работе» через update_request_status снят
        # (у заявителя нет канон-ребра Исполнено→В работе).
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            # AUD3-37: run_command_sync открывает СВОЮ сессию из SessionLocal и
            # весь синхронный — уводим его в поток целиком.
            await asyncio.to_thread(
                run_command_sync,
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=actor_id, source="telegram"),
                ActionCommand(f"revision:{request_number}", Action.APPLICANT_RETURN,
                              {"return_reason": revision_reason}),
            )
        except RequestNotFound:
            await message.answer(get_text("request_reports.handlers.request_not_found", language=language))
            return
        except WorkflowError as e:
            logger.error(f"APPLICANT_RETURN (доработка) отклонён для {request_number}: {e}")
            await message.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)))
            return

        # Добавляем комментарий о доработке
        notices = await run_db(
            lambda s: _add_revision_comment(s, request_number, message.from_user.id, revision_reason), db=_db
        )

        # Доставка — вне сессии, на языке КАЖДОГО получателя (BUG-174)
        from uk_management_bot.services.notification_service import send_to_user

        for notice in notices:
            try:
                await send_to_user(message.bot, notice.telegram_id, notice.text)
            except Exception as notify_error:
                logger.warning(
                    f"Уведомление о комментарии не доставлено tg={notice.telegram_id}: {notify_error}"
                )

        # Показываем подтверждение
        lang = language
        success_text = get_text("reports.revision_requested", language=lang).format(
            request_id=request_number,
            reason=revision_reason
        )

        await message.answer(success_text)

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка сохранения причины доработки: {e}")
        await message.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)))

# Вспомогательные функции

def format_report_for_display(request: Request, report_comments: list, language: str = "ru") -> str:
    """Форматирование отчета для отображения

    Вызывается ИЗ sync-юнита (worker-поток): читает ORM-заявку и lazy-связь
    `comment.user`, поэтому обязана исполняться при живой сессии.
    """
    try:
        # Основная информация о заявке
        report_text = f"📋 **{get_text('request_reports.handlers.report_title', language=language)} #{request.request_number}**\n\n"
        # Категория и статус — через канонические хелперы показа, а не сырыми
        # значениями из БД. Экран отчёта до 2026-07-28 был недостижим из UI
        # (DEAD-134), поэтому дефект никто не видел: категория выводилась ключом
        # («plumbing» вместо «Сантехника»), а статус — русским текстом из БД,
        # то есть UZ-пользователь читал бы его по-русски.
        category_display = get_category_display(
            resolve_category_key(request.category), language=language
        )
        report_text += f"🏷️ **{get_text('request_reports.handlers.category', language=language)}**: {category_display}\n"
        report_text += f"📍 **{get_text('request_reports.handlers.address', language=language)}**: {localize_address(request.address, language)}\n"
        # Секревью A2: свободный текст пользователей — бот шлёт с parse_mode=
        # HTML по умолчанию (класс BUG-174), экранируем все такие подстановки.
        report_text += f"📝 **{get_text('request_reports.handlers.description', language=language)}**: {html.escape(request.description or '')}\n"
        report_text += f"📊 **{get_text('request_reports.handlers.status', language=language)}**: {get_status_display(request.status, language=language)}\n"

        # Информация о выполнении (BUG-153 п.6: канон бизнес-зоны ARCH-116)
        if request.completed_at:
            from uk_management_bot.utils.business_time import fmt_datetime
            report_text += f"✅ **{get_text('request_reports.handlers.completed_at', language=language)}**: {fmt_datetime(request.completed_at)}\n"

        # Отчет о выполнении
        if request.completion_report:
            report_text += f"\n📋 **{get_text('request_reports.handlers.completion_report', language=language)}**:\n{html.escape(request.completion_report)}\n"

        # Материалы для закупки (если были)
        if request.purchase_materials:
            report_text += f"\n🛒 **{get_text('request_reports.handlers.purchase_materials', language=language)}**:\n{html.escape(request.purchase_materials)}\n"

        # Комментарии с отчетами
        if report_comments:
            report_text += f"\n📝 **{get_text('request_reports.handlers.additional_reports', language=language)}**:\n"
            for comment in report_comments[:3]:  # Показываем только последние 3
                user = comment.user.full_name if comment.user else get_text("request_reports.handlers.user_label", language=language).format(user_id=comment.user_id)
                date_str = comment.created_at.strftime('%d.%m.%Y %H:%M') if comment.created_at else get_text("request_reports.handlers.unknown_date", language=language)
                report_text += f"👤 **{html.escape(user)}** ({date_str}):\n{html.escape(comment.comment_text or '')}\n\n"

        return report_text

    except Exception as e:
        logger.error(f"Ошибка форматирования отчета: {e}")
        return get_text("request_reports.handlers.report_format_error", language=language)
