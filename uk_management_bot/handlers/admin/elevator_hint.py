"""Менеджер: подсказка о статусе лифта после подтверждения заявки (Ф4a-2, T7).

После успешного MANAGER_CONFIRM заявки с ``elevator_id`` (admin/views.py)
менеджеру уходит сообщение «Лифт {label}: сейчас «{статус}». Лифт работает?»
с четырьмя статусами (``elv:st:{elevator_id}:{status}:{номер}``) и «Оставить
как есть» (``elv:keep``). Подсказка — источник события, не автосмена (инвариант
модуля): статус меняется только нажатием менеджера через ``set_status_sync``
с ``source="request_hint"`` и номером заявки в журнале.

``set_status_sync`` ничего не отправляет: сообщения жителям подъезда уходят
ПОСЛЕ commit через ``send_notify_messages`` (best-effort). Повтор того же
статуса — идемпотентный no-op (``changed=False``). Всё под
``settings.ELEVATORS_ENABLED``; DB-фаза — sync-юниты под ``run_db``.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from typing import Optional

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.elevators import (
    KEEP_CALLBACK,
    STATUS_PREFIX,
    build_elevator_status_hint_keyboard,
)
from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.services.elevator_service import (
    ElevatorNotFoundError,
    ElevatorStateError,
    ElevatorValidationError,
    elevator_label,
    get_elevator_sync,
    load_config_sync,
    set_status_sync,
    status_label,
)
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.services.workflow_notifications import send_notify_messages
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.utils.helpers import get_text

from ._router import router

logger = logging.getLogger(__name__)

HINT_SOURCE = "request_hint"
_STATUS_RE = re.compile(
    rf"^{re.escape(STATUS_PREFIX)}(?P<id>\d+):(?P<status>[a-z_]+):(?P<number>{REQUEST_NUMBER_CORE})$"
)
STATUS_PATTERN = _STATUS_RE.pattern


# ══════════════════════════════════════════════════════════════════════════
# DTO — пересекают границу run_db
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class HintView:
    elevator_id: int
    label: str
    status: Optional[str]


@dataclass(frozen=True)
class StatusOutcome:
    verdict: str  # changed | unchanged | not_found | rejected
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    messages: tuple[tuple[int, str], ...] = ()


# ══════════════════════════════════════════════════════════════════════════
# Sync-юниты (worker-поток через run_db)
# ══════════════════════════════════════════════════════════════════════════


def _load_hint(db: Session, elevator_id: int, language: str) -> Optional[HintView]:
    try:
        elevator = get_elevator_sync(db, elevator_id)
    except ElevatorNotFoundError:
        return None
    return HintView(elevator.id, elevator_label(elevator, language), elevator.current_status)


def _apply_status(
    db: Session, elevator_id: int, status: str, actor_user_id: Optional[int], request_number: str
) -> StatusOutcome:
    """set_status_sync + commit; сообщения жителям возвращаются, не отправляются."""
    try:
        change = set_status_sync(
            db, elevator_id, status, actor_user_id=actor_user_id, source=HINT_SOURCE,
            request_number=request_number, config=load_config_sync(db),
        )
    except ElevatorNotFoundError:
        return StatusOutcome("not_found")
    except (ElevatorStateError, ElevatorValidationError) as exc:
        AdminHandlerService(db).rollback()
        logger.info("Статус лифта %s из подсказки отклонён: %s", elevator_id, exc)
        return StatusOutcome("rejected")
    if not change.changed:
        return StatusOutcome("unchanged", change.old_status, change.new_status)
    AdminHandlerService(db).commit()
    return StatusOutcome(
        "changed", change.old_status, change.new_status,
        tuple((m.telegram_id, m.text) for m in change.resident_messages),
    )


# ══════════════════════════════════════════════════════════════════════════
# Отправка подсказки (зовётся из views.handle_manager_confirm_completed)
# ══════════════════════════════════════════════════════════════════════════


async def send_elevator_hint(
    bot, chat_id: int, *, elevator_id: Optional[int], request_number: str, lang: str
) -> bool:
    """Best-effort: True, если подсказка отправлена. Без лифта/флага — тихо False."""
    if not settings.ELEVATORS_ENABLED or elevator_id is None:
        return False
    try:
        view = await run_db(lambda s: _load_hint(s, elevator_id, lang))
    except SQLAlchemyError as exc:
        logger.warning("Подсказка о лифте %s: лифт не прочитан: %s", elevator_id, type(exc).__name__)
        return False
    if view is None:
        logger.info("Подсказка о лифте %s пропущена: лифт не найден/архивирован", elevator_id)
        return False
    text = get_text(
        "elevators.hint.prompt", language=lang,
        label=html.escape(view.label), status=html.escape(status_label(view.status, lang)),
    )
    try:
        await bot.send_message(
            chat_id, text, parse_mode="HTML",
            reply_markup=build_elevator_status_hint_keyboard(
                view.elevator_id, request_number, view.status, lang),
        )
    except TelegramAPIError as exc:
        # Текст исключения не логируем: рядом с Bot API он может нести URL с токеном.
        logger.warning("Подсказка о лифте %s не отправлена: %s", elevator_id, type(exc).__name__)
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# Хендлеры
# ══════════════════════════════════════════════════════════════════════════


def _outcome_text(outcome: StatusOutcome, lang: str) -> str:
    if outcome.verdict == "unchanged":
        return get_text("elevators.hint.unchanged", language=lang,
                        status=html.escape(status_label(outcome.new_status, lang)))
    return get_text(
        "elevators.hint.changed", language=lang,
        old=html.escape(status_label(outcome.old_status, lang)),
        new=html.escape(status_label(outcome.new_status, lang)),
    )


async def _edit(callback: CallbackQuery, text: str) -> None:
    """Убрать кнопки и показать итог; сбой Telegram — не ошибка операции."""
    try:
        await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
    except TelegramAPIError as exc:
        logger.warning("Итог подсказки о лифте не показан: %s", type(exc).__name__)
    try:
        await callback.answer()
    except TelegramAPIError as exc:
        logger.debug("callback.answer после подсказки о лифте: %s", type(exc).__name__)


@router.callback_query(F.data.regexp(STATUS_PATTERN))
async def handle_elevator_status_hint(
    callback: CallbackQuery, roles: list = None, user: User = None, language: str = "ru"
) -> None:
    """Кнопка статуса из подсказки: только admin/manager; статус — через set_status_sync."""
    lang = language
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
        return
    match = _STATUS_RE.match(callback.data or "")
    if match is None or match.group("status") not in ELEVATOR_STATUSES:
        # callback_data шлёт КЛИЕНТ — набор статусов проверяется сервером
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)
        return
    elevator_id = int(match.group("id"))
    status, request_number = match.group("status"), match.group("number")
    actor_user_id = user.id if user is not None else None
    try:
        outcome = await run_db(lambda s: _apply_status(
            s, elevator_id, status, actor_user_id, request_number,
        ))
    except SQLAlchemyError as exc:
        logger.error("Смена статуса лифта %s из подсказки упала: %s", elevator_id, exc, exc_info=True)
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)
        return
    if outcome.verdict == "not_found":
        await callback.answer(get_text("elevators.hint.not_found", language=lang), show_alert=True)
        return
    if outcome.verdict == "rejected":
        await callback.answer(get_text("elevators.hint.rejected", language=lang), show_alert=True)
        return
    if outcome.verdict == "changed":
        # ПОСЛЕ commit; хелпер best-effort, не бросает.
        await send_notify_messages(callback.bot, list(outcome.messages))
        logger.info("Лифт %s: статус %s → %s из подсказки по заявке %s (менеджер %s)",
                    elevator_id, outcome.old_status, outcome.new_status, request_number, actor_user_id)
    await _edit(callback, _outcome_text(outcome, lang))


@router.callback_query(F.data == KEEP_CALLBACK)
async def handle_elevator_keep(callback: CallbackQuery, language: str = "ru") -> None:
    """«Оставить как есть»: убрать кнопки, БД не трогаем."""
    await _edit(callback, get_text("elevators.hint.kept", language=language))
