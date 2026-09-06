"""Смена статуса лифта лифтёром с опциональной причиной (Ф5, T10).

``elvm:st:{id}`` → четыре статуса (текущий помечен) → ``elvm:st:{id}:{status}``
→ FSM ``status_reason`` (текст причины или «Без причины») →
``set_status_sync(source="manual", actor)`` в юните → commit → сообщения
жителям через ``send_notify_messages`` ПОСЛЕ commit (best-effort) → итог
«X → Y (уведомлено: N)» и свежая карточка. ``change_status`` переиспользует
``repair.py`` (предложение «В ремонте» после создания заявки).
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Union

from aiogram import Bot, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES
from uk_management_bot.database.session import run_db
from uk_management_bot.services.elevator_service import MAX_REASON_LEN
from uk_management_bot.services.workflow_notifications import send_notify_messages
from uk_management_bot.states.elevators import ElevatorStates

from . import _common
from ._common import RunDb
from ._keyboards import NO_REASON_CB, STATUS_PREFIX, reason_keyboard, statuses_keyboard
from ._router import router
from ._texts import deny_text, status_outcome_text, t
from ._units import OK, StatusOutcome, apply_status

logger = logging.getLogger(__name__)

_MENU_RE = re.compile(rf"^{re.escape(STATUS_PREFIX)}(?P<id>\d+)$")
_PICK_RE = re.compile(rf"^{re.escape(STATUS_PREFIX)}(?P<id>\d+):(?P<status>[a-z_]+)$")
_SHOWN_VERDICTS = ("changed", "unchanged")

Event = Union[CallbackQuery, Message]


async def change_status(
    run: RunDb, bot: Bot, telegram_id: int, elevator_id: int, status: str, *,
    reason: Optional[str], request_number: Optional[str],
) -> tuple[StatusOutcome, int]:
    """Юнит смены статуса + отправка сообщений жителям после commit; -> (итог, отправлено)."""
    outcome = await _common.run_unit(run, lambda s: apply_status(
        s, telegram_id, elevator_id, status, reason=reason, request_number=request_number,
    ), "смена статуса лифта")
    if outcome is None:
        return StatusOutcome("error"), 0
    if outcome.verdict != "changed":
        return outcome, 0
    # ПОСЛЕ commit; без адресатов (not_working / уведомление выключено) — без сети.
    sent = await send_notify_messages(bot, list(outcome.messages)) if outcome.messages else 0
    logger.info("Лифт %s: статус %s → %s вручную (tg=%s, заявка %s, жителей уведомлено %s)",
                elevator_id, outcome.old_status, outcome.new_status, telegram_id, request_number, sent)
    return outcome, sent


async def present_outcome(
    run: RunDb, event: Event, outcome: StatusOutcome, sent: int, elevator_id: int, language: str,
    *, is_callback: bool,
) -> None:
    """Итог: callback — редактируем сообщение, текст — отвечаем; затем карточка."""
    if outcome.verdict not in _SHOWN_VERDICTS:
        if is_callback:
            await _common.deny(event, outcome.verdict, language)
        else:
            await event.answer(deny_text(outcome.verdict, language))
        return
    text = status_outcome_text(outcome, sent, language)
    if is_callback:
        await _common.edit(event, text)
        message = event.message
    else:
        await event.answer(text, parse_mode="HTML")
        message = event
    await _common.answer_card(run, message, event.from_user.id, elevator_id, language)


@router.callback_query(F.data.regexp(_MENU_RE.pattern))
async def handle_status_menu(callback: CallbackQuery, language: str = "ru") -> None:
    """``elvm:st:{id}``: клавиатура статусов; невведённый лифт — отказ."""
    match = _MENU_RE.match(callback.data or "")
    elevator_id = _common.parse_int(match.group("id")) if match else None
    if elevator_id is None:
        await _common.deny(callback, "error", language)
        return
    view = await _common.load_card_view(run_db, callback.from_user.id, elevator_id, language)
    if view.verdict != OK:
        await _common.deny(callback, view.verdict, language)
        return
    if not view.is_commissioned:
        await callback.answer(t("status_not_commissioned", language), show_alert=True)
        return
    await _common.edit(callback, t("status_prompt", language),
                    statuses_keyboard(elevator_id, view.status, language))


@router.callback_query(F.data.regexp(_PICK_RE.pattern))
async def handle_status_pick(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:st:{id}:{status}``: статус проверен сервером → шаг причины."""
    match = _PICK_RE.match(callback.data or "")
    elevator_id = _common.parse_int(match.group("id")) if match else None
    status = match.group("status") if match else None
    if elevator_id is None or status not in ELEVATOR_STATUSES:
        # callback_data шлёт КЛИЕНТ — набор статусов проверяется сервером
        await _common.deny(callback, "error", language)
        return
    await state.clear()
    await state.update_data(elvm_elevator_id=elevator_id, elvm_status=status)
    await state.set_state(ElevatorStates.status_reason)
    await _common.edit(callback, t("reason_prompt", language), reason_keyboard(language))


async def _finish(
    event: Event, state: FSMContext, reason: Optional[str], language: str, *, is_callback: bool
) -> None:
    data = await state.get_data()
    await state.clear()
    elevator_id, status = data.get("elvm_elevator_id"), data.get("elvm_status")
    if elevator_id is None or status is None:
        # Осиротевшее состояние (данные потеряны) — сброс, не падение.
        if is_callback:
            await _common.cancelled(event, language)
        else:
            await event.answer(t("cancelled", language))
        return
    outcome, sent = await change_status(
        run_db, event.bot, event.from_user.id, int(elevator_id), str(status),
        reason=reason, request_number=None,
    )
    await present_outcome(run_db, event, outcome, sent, int(elevator_id), language,
                          is_callback=is_callback)


@router.message(StateFilter(ElevatorStates.status_reason), F.text)
async def handle_reason_text(message: Message, state: FSMContext, language: str = "ru") -> None:
    """Причина текстом; длиннее ``MAX_REASON_LEN`` — переспрос."""
    reason = (message.text or "").strip()
    if len(reason) > MAX_REASON_LEN:
        await message.answer(t("reason_too_long", language, max=MAX_REASON_LEN))
        return
    await _finish(message, state, reason or None, language, is_callback=False)


@router.callback_query(StateFilter(ElevatorStates.status_reason), F.data == NO_REASON_CB)
async def handle_no_reason(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """«Без причины»: применить статус без reason."""
    await _finish(callback, state, None, language, is_callback=True)
