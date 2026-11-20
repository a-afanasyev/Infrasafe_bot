"""Разделяемое для admin-пакета: SSOT-константы кнопок, ManagerStates, auto_assign_request_by_category (AUD3-06)."""
import html
import os
from typing import Optional

from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.constants.categories import get_specialization_for_category

import logging
from uk_management_bot.database.session import run_db
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display, get_urgency_display
from uk_management_bot.utils.twa_links import executor_task_open_markup
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.utils.button_texts import (
    get_admin_panel_texts,
    get_admin_user_management_texts,
    get_admin_employee_management_texts,
    get_admin_new_requests_texts,
    get_admin_active_requests_texts,
    get_admin_completed_requests_texts,
    get_admin_awaiting_review_texts,
    get_admin_returned_texts,
    get_admin_not_accepted_texts,
    get_admin_back_to_menu_texts,
    get_admin_archive_texts,
    get_admin_purchase_texts,
    get_admin_create_invite_texts,
    get_admin_shifts_texts,
)

logger = logging.getLogger(__name__)


# PR-25 (BUG-BOT-034): manager accept_/purchase_ actions bound to the shared
# request-number core (strict regex) instead of open-set startswith+exclusion
# lambdas, so accept_request_ and any future accept_*/purchase_* callbacks
# fall through to their own handlers instead of being swallowed here
# (the purchase_materials_ handler itself was retired as dead code, BUG-137).
_ACCEPT_REQUEST_NUMBER_RE = rf"^accept_{REQUEST_NUMBER_CORE}$"
_PURCHASE_REQUEST_NUMBER_RE = rf"^purchase_{REQUEST_NUMBER_CORE}$"

# Single Source of Truth for button texts - TASK 17
ADMIN_PANEL_TEXTS = get_admin_panel_texts()
ADMIN_USER_MANAGEMENT_TEXTS = get_admin_user_management_texts()
ADMIN_EMPLOYEE_MANAGEMENT_TEXTS = get_admin_employee_management_texts()
ADMIN_NEW_REQUESTS_TEXTS = get_admin_new_requests_texts()
ADMIN_ACTIVE_REQUESTS_TEXTS = get_admin_active_requests_texts()
ADMIN_COMPLETED_REQUESTS_TEXTS = get_admin_completed_requests_texts()
ADMIN_AWAITING_REVIEW_TEXTS = get_admin_awaiting_review_texts()
ADMIN_RETURNED_TEXTS = get_admin_returned_texts()
ADMIN_NOT_ACCEPTED_TEXTS = get_admin_not_accepted_texts()
ADMIN_BACK_TO_MENU_TEXTS = get_admin_back_to_menu_texts()
ADMIN_ARCHIVE_TEXTS = get_admin_archive_texts()
ADMIN_PURCHASE_TEXTS = get_admin_purchase_texts()
ADMIN_CREATE_INVITE_TEXTS = get_admin_create_invite_texts()
ADMIN_SHIFTS_TEXTS = get_admin_shifts_texts()

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()
    waiting_for_clarification_text = State()
    waiting_for_materials_edit = State()


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

# Исходы группового назначения. Раньше функция на ВСЕХ ветках просто
# возвращала None, и хендлер печатал «✅ назначена» одинаково — в том числе
# когда не сделал ничего: заявка уже назначена, специализации у категории нет,
# исполнителей нет. Молчащий флоу выглядел работающим, менеджер уходил с
# ложным подтверждением. Исход возвращается наружу, чтобы каждая ветка имела
# свой текст.
ASSIGN_OK = "assigned"
ASSIGN_ALREADY_INDIVIDUAL = "already_assigned_individual"
ASSIGN_ALREADY_GROUP = "already_assigned_group"
ASSIGN_NO_SPECIALIZATION = "no_specialization"
ASSIGN_NO_EXECUTORS = "no_executors"
ASSIGN_ERROR = "error"


async def auto_assign_request_by_category(request: Request, db: Session, manager: User) -> str:
    """
    Автоматически назначает заявку исполнителям по категории/специализации

    Args:
        request: Заявка для назначения
        db: Сессия базы данных
        manager: Менеджер, который назначает заявку

    Returns:
        Один из ASSIGN_* — что именно произошло. Вызывающий обязан различать
        исходы: «уже назначена» и «нет исполнителей» — не успех.
    """
    try:
        logger.info(f"[AUTO_ASSIGN] Начало автоматического назначения для заявки {request.request_number}, категория: {request.category}")

        # Специализация по категории — только через хелпер: legacy RU-лейблы
        # резолвятся, неизвестная категория уходит к разнорабочему. Пустая
        # категория — единственный путь в ASSIGN_NO_SPECIALIZATION.
        specialization = (
            get_specialization_for_category(request.category) if request.category else None
        )
        logger.info(f"[AUTO_ASSIGN] Категория '{request.category}' → специализация: {specialization}")

        if not specialization:
            logger.warning(f"[AUTO_ASSIGN] Пустая категория заявки {request.request_number}")
            return ASSIGN_NO_SPECIALIZATION
        
        # Находим исполнителей с нужной специализацией
        logger.info("[AUTO_ASSIGN] Выполнение запроса к таблице users...")

        # AUD3-01: кандидаты — по roles-массиву (исполнитель может быть с активной
        # ролью applicant), НЕ по active_role; специализации — единый парсер
        # (JSON-list/CSV/скаляр) вместо локального json.loads.
        from uk_management_bot.utils.auth_helpers import get_user_roles
        from uk_management_bot.utils.constants import ROLE_EXECUTOR
        from uk_management_bot.utils.specializations import parse_specializations

        svc = AdminHandlerService(db)

        # Состояние заявки первично по отношению к наличию людей: если заявка
        # уже назначена, менеджеру надо сказать именно это, а не «нет
        # подходящих исполнителей» — иначе при пустой специализации он получал
        # чужой диагноз и не понимал, что делать.
        existing_assignment = svc.get_active_assignment(request.request_number)
        if existing_assignment:
            logger.info(f"[AUTO_ASSIGN] Заявка {request.request_number} уже назначена (ID: {existing_assignment.id}), пропускаем")
            return ASSIGN_ALREADY_INDIVIDUAL

        existing_group_assignment = svc.get_active_group_assignment(
            request.request_number, specialization
        )
        if existing_group_assignment:
            logger.info(f"[AUTO_ASSIGN] Заявка {request.request_number} уже назначена группе {specialization}, пропускаем")
            return ASSIGN_ALREADY_GROUP

        approved_users = svc.list_approved_users()
        logger.info(f"[AUTO_ASSIGN] Approved-пользователей всего: {len(approved_users)}")

        # BUG-166: общий предикат. `auto_manager/rule_engine.select_executor`
        # построен как зеркало этой функции — оставить здесь голое `in` значило
        # бы развести зеркала по трактовке джокера `universal`.
        from uk_management_bot.utils.specializations import matches_required_specs
        matching_executors = [
            ex for ex in approved_users
            if ROLE_EXECUTOR in get_user_roles(ex)
            and matches_required_specs(parse_specializations(ex), {specialization})
        ]

        logger.info(f"[AUTO_ASSIGN] Найдено {len(matching_executors)} подходящих исполнителей для специализации '{specialization}'")

        if not matching_executors:
            logger.warning(f"[AUTO_ASSIGN] Не найдено исполнителей для специализации {specialization}")
            return ASSIGN_NO_EXECUTORS
        
        logger.info(f"[AUTO_ASSIGN] Назначений для заявки {request.request_number} не найдено, создаем новое групповое назначение")

        # SSOT-кластер #1, PR2d: запись назначения (RequestAssignment +
        # request.assignment_type/assigned_group/assigned_at/assigned_by) через
        # allowlist-слой assignment_service вместо сырого ORM в хендлере.
        from uk_management_bot.services.assignment_service import AssignmentService
        AssignmentService(db).assign_to_group(request.request_number, specialization, manager.id)
        svc.refresh(request)

        logger.info(f"[AUTO_ASSIGN] ✅ Заявка {request.request_number} автоматически назначена группе {specialization} ({len(matching_executors)} исполнителей)")

        # BUG-185: уведомления ВСЕЙ группе живут здесь (единственный живой
        # вызывающий assign_to_group). Дежурным — богатый наряд, остальным
        # подходящим — лёгкое «в вашей группе новая заявка»: раньше их звал
        # несуществующий NotificationService.send_notification внутри сервиса,
        # AttributeError гасился except'ом, и исполнители без смены не узнавали
        # о заявке никогда. Оба текста — на языке ПОЛУЧАТЕЛЯ; свободные
        # подстановки (адрес/описание/категория-fallback) экранируются: сырой
        # '<' давал Telegram-400, и уведомление молча терялось (канон BUG-174).
        from datetime import datetime as dt

        from uk_management_bot.handlers.shift_management.shared import (
            translate_specializations,
        )
        from uk_management_bot.services.notification_service import _get_shared_bot

        bot = _get_shared_bot()
        now = dt.now()

        for executor in matching_executors:
            active_shift = svc.get_active_shift_for(executor.id, now)
            lang = executor.language or "ru"
            reply_markup = None
            try:
                if active_shift:
                    # Дежурному групповая заявка доступна (канон request_access) —
                    # web_app «Открыть» на карточку в TWA (шлём в личку). Без смены
                    # карточка ответит 403 — кнопки нет.
                    reply_markup = executor_task_open_markup(request.request_number, lang)
                    notification_text = get_text("admin.handlers.new_request_for_duty", language=lang).format(
                        specialization=translate_specializations([specialization], lang),
                        request_number=request.request_number,
                        category=html.escape(get_category_display(resolve_category_key(request.category), language=lang)),
                        address=html.escape(request.address or ""),
                        urgency=html.escape(get_urgency_display(request.urgency, language=lang)) if request.urgency else "",
                        description=html.escape(request.description or "")
                    )
                else:
                    notification_text = get_text("admin.handlers.new_request_for_group", language=lang).format(
                        specialization=translate_specializations([specialization], lang),
                        request_number=request.request_number,
                        category=html.escape(get_category_display(resolve_category_key(request.category), language=lang)),
                        address=html.escape(request.address or "")
                    )
                await bot.send_message(
                    chat_id=executor.telegram_id,
                    text=notification_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                logger.info(f"Уведомление о групповом назначении отправлено исполнителю {executor.id} (смена {active_shift.id if active_shift else '—'})")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления исполнителю {executor.id}: {e}")

        return ASSIGN_OK

    except Exception as e:
        logger.error(f"Ошибка автоматического назначения заявки {request.request_number}: {e}")
        return ASSIGN_ERROR


PROMPT_MESSAGE_KEY = "prompt_message_id"


async def remember_prompt(callback, state) -> None:
    """Запомнить сообщение, в котором бот спросил причину/текст.

    Карточка заявки (или карточка-уведомление) при нажатии «Вернуть в работу»,
    «Уточнить», «Отклонить» превращается в подсказку с кнопкой «Отмена». Её id
    нужен, чтобы после ввода текста записать итог в НЕЁ ЖЕ, а не оставить
    висеть с кнопкой отмены уже завершённого действия.
    """
    await state.update_data(**{PROMPT_MESSAGE_KEY: callback.message.message_id})


async def close_prompt(message, state, text: Optional[str] = None) -> bool:
    """Закрыть подсказку: записать в неё итог (или просто снять кнопки).

    Звать ДО `state.clear()`. True — подсказка обновлена, отдельное сообщение с
    тем же текстом слать не нужно; False — подсказки нет или Telegram отказал
    (сообщение удалено/слишком старое), вызывающий отвечает как раньше.
    """
    prompt_id = (await state.get_data()).get(PROMPT_MESSAGE_KEY)
    if not prompt_id:
        return False
    try:
        if text is None:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id, message_id=prompt_id, reply_markup=None)
        else:
            await message.bot.edit_message_text(
                text=text, chat_id=message.chat.id, message_id=prompt_id)
        return True
    except TelegramAPIError as exc:
        logger.info("Подсказка %s не обновлена: %s", prompt_id, type(exc).__name__)
        return False


def is_stale_refusal(exc: Exception) -> bool:
    """Канон отказал из-за СОСТОЯНИЯ заявки (её уже кто-то обработал), а не
    из-за прав или данных команды.

    Только на такой отказ уместно «Уже обработано». `NotAuthorized` (админ без
    роли менеджера), `PayloadInvalid` и прочее — другая причина, и говорить
    «уже обработано» про заявку, которую никто не трогал, значит соврать.
    """
    from uk_management_bot.utils.request_workflow.types import (
        InvalidTransition,
        RepeatConflict,
        RepeatRejected,
    )

    return isinstance(exc, (InvalidTransition, RepeatRejected, RepeatConflict))


def current_status_label(db: Session, request_number: str, lang: str) -> str:
    """Sync-юнит (под `run_db`): подпись текущего статуса заявки."""
    request = AdminHandlerService(db).get_request_by_number(request_number)
    return get_status_display(request.status, language=lang) if request else "—"


async def already_handled_text(request_number: str, lang: str, *, _db=None) -> str:
    """«Уже обработано: <статус>» — ответ на действие, которое канон отклонил,
    потому что заявку успел обработать кто-то другой."""
    status = await run_db(lambda s: current_status_label(s, request_number, lang), db=_db)
    return get_text("notifications.manager.already_handled", language=lang, status=status)


def delete_admin_ids() -> frozenset:
    """Telegram-id администраторов из ADMIN_USER_IDS — только они удаляют заявки.

    Читается из окружения при каждом вызове, как раньше делал сам хендлер
    удаления. Один источник для хендлера и для карточки: кнопку «Удалить»
    не рисуем тем, кого хендлер всё равно не пустит.
    """
    raw = os.getenv("ADMIN_USER_IDS", "")
    # Мусор в переменной не должен ломать карточку заявки: нечисловые части
    # пропускаются (такой id всё равно никому не принадлежит).
    return frozenset(int(part) for part in raw.split(",") if part.strip().isdigit())
