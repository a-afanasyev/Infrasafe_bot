"""Создание заявки на ремонт лифта из карточки (Ф5, T10).

``elvm:rep:{id}`` → FSM ``repair_description`` (≥ ``MIN_DESCRIPTION_LEN``) →
``repair_urgency`` (канон срочности под ``elvm:urg:``) → штатный
``save_request`` с ``category="elevator"``, адресом дома
(``address_type="building"``, роль ``staff_group`` — уровень дома без
принадлежности, как staff-репорт Group Intake), ``elevator_id``,
``elevator_operational=False``, ``acceptance_mode="manager"``. Автодиспетчер
вызывает сам ``save_request_sync`` после commit — особых правил нет. После
создания — предложение «Поставить лифту „В ремонте“?» (``elvm:repst:...``),
«Да» — ``status.change_status`` с reason «ремонт {номер}» и номером в журнале.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from aiogram import F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from uk_management_bot.database.session import run_db
from uk_management_bot.handlers.requests.create import save_request
from uk_management_bot.services.elevator_service import ELEVATOR_CATEGORY
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.states.elevators import ElevatorStates
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_MANAGER, URGENCY_VALUES

from . import _common, status
from ._keyboards import (
    REPAIR_PREFIX,
    REPAIR_STATUS_PREFIX,
    URGENCY_PREFIX,
    cancel_keyboard,
    repair_status_offer_keyboard,
    urgency_keyboard,
)
from ._router import router
from ._texts import repair_created_text, t
from ._units import OK, Access, check_access

logger = logging.getLogger(__name__)

MIN_DESCRIPTION_LEN = 10
UNDER_REPAIR = "under_repair"
# Роль резолва адреса: уровень дома без требования принадлежности (services/request_address).
REPAIR_ROLE = "staff_group"
REPAIR_SOURCE = "bot"

_START_RE = re.compile(rf"^{re.escape(REPAIR_PREFIX)}(?P<id>\d+)$")
_URGENCY_RE = re.compile(rf"^{re.escape(URGENCY_PREFIX)}(?P<key>[a-z]+)$")
_OFFER_RE = re.compile(
    rf"^{re.escape(REPAIR_STATUS_PREFIX)}(?P<id>\d+):(?P<number>{REQUEST_NUMBER_CORE}):(?P<yes>[01])$"
)


def build_repair_data(
    *, building_id: int, elevator_id: int, description: str, urgency: str, reporter_id: Optional[int],
) -> dict:
    """``data`` для ``save_request``: контракт лифтовой заявки лифтёра."""
    return {
        "category": ELEVATOR_CATEGORY,
        "address_type": "building",
        "address_id": building_id,
        "building_id": building_id,
        "description": description,
        "urgency": urgency,
        "elevator_id": elevator_id,
        "elevator_operational": False,
        "acceptance_mode": ACCEPTANCE_MODE_MANAGER,
        "reported_by_user_id": reporter_id,
    }


@router.callback_query(F.data.regexp(_START_RE.pattern))
async def handle_repair_start(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:rep:{id}``: гейт + дом лифта в FSM → шаг описания."""
    match = _START_RE.match(callback.data or "")
    elevator_id = _common.parse_int(match.group("id")) if match else None
    if elevator_id is None:
        await _common.deny(callback, "error", language)
        return
    view = await _common.load_card_view(run_db, callback.from_user.id, elevator_id, language)
    if view.verdict != OK:
        await _common.deny(callback, view.verdict, language)
        return
    if not view.is_commissioned:
        # Кнопки в карточке нет, но устаревшая карточка / crafted callback — явный отказ.
        await callback.answer(t("repair_not_commissioned", language), show_alert=True)
        return
    await state.clear()
    await state.update_data(elvm_elevator_id=view.id, elvm_building_id=view.building_id)
    await state.set_state(ElevatorStates.repair_description)
    await _common.edit(callback, t("repair_description_prompt", language, min=MIN_DESCRIPTION_LEN),
                    cancel_keyboard(language))


@router.message(StateFilter(ElevatorStates.repair_description), F.text)
async def handle_description(message: Message, state: FSMContext, language: str = "ru") -> None:
    """Описание неисправности; короче ``MIN_DESCRIPTION_LEN`` — переспрос."""
    description = (message.text or "").strip()
    if len(description) < MIN_DESCRIPTION_LEN:
        await message.answer(t("repair_description_short", language, min=MIN_DESCRIPTION_LEN))
        return
    await state.update_data(elvm_description=description)
    await state.set_state(ElevatorStates.repair_urgency)
    await message.answer(t("repair_urgency_prompt", language), reply_markup=urgency_keyboard(language))


async def _reporter(telegram_id: int) -> Access:
    access = await _common.run_unit(run_db, lambda s: check_access(s, telegram_id), "гейт лифтёра")
    return access if access is not None else Access("error")


@router.callback_query(StateFilter(ElevatorStates.repair_urgency), F.data.regexp(_URGENCY_RE.pattern))
async def handle_urgency(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:urg:{key}``: срочность → ``save_request`` → предложение статуса «В ремонте»."""
    match = _URGENCY_RE.match(callback.data or "")
    urgency = match.group("key") if match else None
    if urgency not in URGENCY_VALUES:
        await _common.deny(callback, "error", language)
        return
    data = await state.get_data()
    await state.clear()
    elevator_id, building_id = data.get("elvm_elevator_id"), data.get("elvm_building_id")
    description = data.get("elvm_description")
    if elevator_id is None or building_id is None or not description:
        await _common.cancelled(callback, language)
        return
    access = await _reporter(callback.from_user.id)
    if access.verdict != OK:
        await _common.deny(callback, access.verdict, language)
        return
    request_data = build_repair_data(
        building_id=int(building_id), elevator_id=int(elevator_id), description=str(description),
        urgency=urgency, reporter_id=access.user_id,
    )
    number = await save_request(request_data, callback.from_user.id, None, callback.bot,
                                source=REPAIR_SOURCE, role=REPAIR_ROLE)
    if not number:
        await _common.edit(callback, t("repair_failed", language))
        return
    logger.info("Лифтёр tg=%s создал ремонт %s по лифту %s", callback.from_user.id, number, elevator_id)
    await _common.edit(callback, repair_created_text(number, language),
                    repair_status_offer_keyboard(int(elevator_id), number, language))


@router.callback_query(F.data.regexp(_OFFER_RE.pattern))
async def handle_repair_status_offer(callback: CallbackQuery, language: str = "ru") -> None:
    """``elvm:repst:{id}:{номер}:1|0``: «Да» — статус «В ремонте» с номером заявки в журнале."""
    match = _OFFER_RE.match(callback.data or "")
    if match is None:
        await _common.deny(callback, "error", language)
        return
    elevator_id, number = int(match.group("id")), match.group("number")
    if match.group("yes") == "0":
        await _common.edit(callback, t("repair_status_kept", language))
        await _common.answer_card(run_db, callback.message, callback.from_user.id, elevator_id, language)
        return
    outcome, sent = await status.change_status(
        run_db, callback.bot, callback.from_user.id, elevator_id, UNDER_REPAIR,
        reason=t("repair_reason", language, number=number), request_number=number,
    )
    await status.present_outcome(run_db, callback, outcome, sent, elevator_id, language,
                                 is_callback=True)
