"""Отметка ТО / освидетельствования выполненным (Ф5, T10).

``elvm:occs:{id}`` → planned-пункты лифта обоих видов (просроченные помечены)
→ ``elvm:occ:{oid}:done`` → FSM ``occ_comment`` (текст или «Пропустить») →
для освидетельствования: номер акта → срок ДД.ММ.ГГГГ → ссылка (опц.) →
``complete_occurrence_sync`` в юните → «Выполнено, следующее ТО: {дата}».
Валидация ссылки — сервисной ``validate_url`` до записи, чтобы переспросить,
а не показать сырой текст доменной ошибки.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Optional, Union

from aiogram import F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.session import run_db
from uk_management_bot.services.elevator_service import ElevatorValidationError, validate_url
from uk_management_bot.services.elevator_service.calendar import KIND_CERTIFICATION
from uk_management_bot.services.elevator_service.validation_db import cert_act_url_max_len
from uk_management_bot.states.elevators import ElevatorStates

from . import card
from ._keyboards import (
    OCCURRENCE_DONE_SUFFIX,
    OCCURRENCE_PREFIX,
    OCCURRENCES_PREFIX,
    SKIP_CB,
    cancel_keyboard,
    occurrences_keyboard,
    skip_cancel_keyboard,
)
from ._router import router
from ._texts import deny_text, occ_done_text, t
from ._units import OK, complete_occurrence, load_occurrence, load_occurrences

logger = logging.getLogger(__name__)

DATE_FORMAT = "%d.%m.%Y"
CERT_NUMBER_MAX_LEN = Elevator.__table__.c.cert_number.type.length
ALL_STATES = tuple(
    getattr(ElevatorStates, name) for name in (
        "status_reason", "repair_description", "repair_urgency",
        "occ_comment", "cert_number", "cert_valid_until", "cert_url",
    )
)

_LIST_RE = re.compile(rf"^{re.escape(OCCURRENCES_PREFIX)}(?P<id>\d+)$")
_PICK_RE = re.compile(
    rf"^{re.escape(OCCURRENCE_PREFIX)}(?P<id>\d+){re.escape(OCCURRENCE_DONE_SUFFIX)}$"
)

Event = Union[CallbackQuery, Message]


async def _say(event: Event, text: str, markup=None, *, is_callback: bool) -> None:
    """Ответ шага: callback — редактируем, текст — новое сообщение."""
    if is_callback:
        await card.edit(event, text, markup)
    else:
        await event.answer(text, reply_markup=markup, parse_mode="HTML")


def parse_cert_date(raw: str) -> Optional[date]:
    try:
        return datetime.strptime(raw.strip(), DATE_FORMAT).date()
    except ValueError:
        return None


def cert_fields_from(data: dict) -> Optional[dict[str, Any]]:
    """Поля освидетельствования из FSM; ``None`` для ТО."""
    if data.get("elvm_kind") != KIND_CERTIFICATION:
        return None
    fields: dict[str, Any] = {
        "cert_number": data.get("elvm_cert_number"),
        "cert_valid_until": date.fromisoformat(data["elvm_cert_valid_until"])
        if data.get("elvm_cert_valid_until") else None,
    }
    if data.get("elvm_cert_url"):
        fields["cert_act_url"] = data["elvm_cert_url"]
    return fields


@router.callback_query(F.data.regexp(_LIST_RE.pattern))
async def handle_occurrences(callback: CallbackQuery, language: str = "ru") -> None:
    """``elvm:occs:{id}``: planned-пункты графика лифта."""
    match = _LIST_RE.match(callback.data or "")
    elevator_id = card.parse_int(match.group("id")) if match else None
    if elevator_id is None:
        await card.deny(callback, "error", language)
        return
    view = await card.run_unit(
        run_db, lambda s: load_occurrences(s, callback.from_user.id, elevator_id), "график лифта")
    if view is None or view.verdict != OK:
        await card.deny(callback, view.verdict if view else "error", language)
        return
    text = t("occ_title", language) if view.rows else t("occ_none", language)
    await card.edit(callback, text, occurrences_keyboard(elevator_id, view.rows, language))


@router.callback_query(F.data.regexp(_PICK_RE.pattern))
async def handle_occurrence_pick(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:occ:{oid}:done``: пункт проверен сервером (planned) → шаг комментария."""
    match = _PICK_RE.match(callback.data or "")
    occurrence_id = card.parse_int(match.group("id")) if match else None
    if occurrence_id is None:
        await card.deny(callback, "error", language)
        return
    target = await card.run_unit(
        run_db, lambda s: load_occurrence(s, callback.from_user.id, occurrence_id), "пункт графика")
    if target is None or target.verdict != OK:
        await card.deny(callback, target.verdict if target else "error", language)
        return
    await state.clear()
    await state.update_data(elvm_occurrence_id=target.id, elvm_elevator_id=target.elevator_id,
                            elvm_kind=target.kind)
    await state.set_state(ElevatorStates.occ_comment)
    await card.edit(callback, t("occ_comment_prompt", language), skip_cancel_keyboard(language))


async def _after_comment(event: Event, state: FSMContext, language: str, *, is_callback: bool) -> None:
    data = await state.get_data()
    if data.get("elvm_kind") == KIND_CERTIFICATION:
        await state.set_state(ElevatorStates.cert_number)
        await _say(event, t("cert_number_prompt", language), cancel_keyboard(language),
                   is_callback=is_callback)
        return
    await _complete(event, state, language, is_callback=is_callback)


async def _complete(event: Event, state: FSMContext, language: str, *, is_callback: bool) -> None:
    data = await state.get_data()
    await state.clear()
    occurrence_id = data.get("elvm_occurrence_id")
    if occurrence_id is None:
        await _say(event, t("cancelled", language), is_callback=is_callback)
        return
    outcome = await card.run_unit(run_db, lambda s: complete_occurrence(
        s, event.from_user.id, int(occurrence_id),
        comment=data.get("elvm_comment"), cert_fields=cert_fields_from(data),
    ), "закрытие пункта графика")
    if outcome is None or outcome.verdict != "done":
        verdict = outcome.verdict if outcome else "error"
        if is_callback:
            await card.deny(event, verdict, language)
        else:
            await event.answer(deny_text(verdict, language))
        return
    logger.info("Лифтёр tg=%s закрыл пункт графика %s (лифт %s)",
                event.from_user.id, occurrence_id, outcome.elevator_id)
    await _say(event, occ_done_text(outcome, language), is_callback=is_callback)
    message = event.message if is_callback else event
    await card.answer_card(run_db, message, event.from_user.id, outcome.elevator_id, language)


@router.message(StateFilter(ElevatorStates.occ_comment), F.text)
async def handle_comment_text(message: Message, state: FSMContext, language: str = "ru") -> None:
    await state.update_data(elvm_comment=(message.text or "").strip() or None)
    await _after_comment(message, state, language, is_callback=False)


@router.callback_query(
    StateFilter(ElevatorStates.occ_comment, ElevatorStates.cert_url), F.data == SKIP_CB
)
async def handle_skip(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """«Пропустить»: без комментария (шаг комментария) или без ссылки (шаг ссылки)."""
    if await state.get_state() == ElevatorStates.cert_url.state:
        await _complete(callback, state, language, is_callback=True)
        return
    await state.update_data(elvm_comment=None)
    await _after_comment(callback, state, language, is_callback=True)


@router.message(StateFilter(ElevatorStates.cert_number), F.text)
async def handle_cert_number(message: Message, state: FSMContext, language: str = "ru") -> None:
    number = (message.text or "").strip()
    if not number or len(number) > CERT_NUMBER_MAX_LEN:
        await message.answer(t("cert_number_invalid", language, max=CERT_NUMBER_MAX_LEN))
        return
    await state.update_data(elvm_cert_number=number)
    await state.set_state(ElevatorStates.cert_valid_until)
    await message.answer(t("cert_valid_until_prompt", language), reply_markup=cancel_keyboard(language))


@router.message(StateFilter(ElevatorStates.cert_valid_until), F.text)
async def handle_cert_date(message: Message, state: FSMContext, language: str = "ru") -> None:
    valid_until = parse_cert_date(message.text or "")
    if valid_until is None:
        await message.answer(t("cert_date_invalid", language))
        return
    await state.update_data(elvm_cert_valid_until=valid_until.isoformat())
    await state.set_state(ElevatorStates.cert_url)
    await message.answer(t("cert_url_prompt", language), reply_markup=skip_cancel_keyboard(language))


@router.message(StateFilter(ElevatorStates.cert_url), F.text)
async def handle_cert_url(message: Message, state: FSMContext, language: str = "ru") -> None:
    url = (message.text or "").strip()
    try:
        validate_url(url, "cert_act_url", max_len=cert_act_url_max_len())
    except ElevatorValidationError:
        await message.answer(t("cert_url_invalid", language))
        return
    await state.update_data(elvm_cert_url=url)
    await _complete(message, state, language, is_callback=False)


@router.message(StateFilter(*ALL_STATES))
async def handle_non_text(message: Message, language: str = "ru") -> None:
    """Не текст на текстовом шаге лифтёра — подсказка, состояние сохраняется."""
    await message.answer(t("text_only", language))
