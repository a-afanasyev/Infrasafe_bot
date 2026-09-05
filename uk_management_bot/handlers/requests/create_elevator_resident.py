"""Поток жителя на лифтовом шаге (Ф4a-2, T7): ``RESIDENT_FLOW`` + тонкие хендлеры.

Общие шаги, DTO и sync-юниты — в ``create_elevator.py``; здесь только то, чем
житель отличается от обходчика: состояния ``RequestStates.elevator_pick`` /
``elevator_operational``, роль ``applicant``, клавиатура категорий жителя,
реакция на двор («укажите дом» + переотправка адресов) и отмена через
``create.cancel_request``. Регистрируется в пакете ``handlers/requests``
(``__init__``); фильтры по состоянию — перехвата чужих ``elv:*`` нет.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.elevators import OPERATIONAL_PREFIX, PICK_PREFIX
from uk_management_bot.keyboards.requests import (
    build_request_address_inline_keyboard,
    get_categories_inline_keyboard_with_cancel,
)
from uk_management_bot.utils.helpers import get_text

from ._router import router
from .create_elevator import (
    ElevatorFlow,
    elevator_step_text,
    operational_step,
    pick_elevator_step,
)
from .shared import (
    RequestStates,
    _deny_if_pending_callback,
    _get_user_language,
    _has_any_address,
    _load_user_request_addresses,
)

logger = logging.getLogger(__name__)


async def _resident_no_building(callback: CallbackQuery, language: str) -> None:
    """Двор не годится: попросить дом/квартиру и переотправить кнопки адресов."""
    await callback.message.answer(get_text("requests.elevator.need_building", language=language))
    addresses = await run_db(lambda s: _load_user_request_addresses(s, callback.from_user.id))
    if _has_any_address(addresses):
        await callback.message.answer(
            get_text("requests.choose_address_prompt", language=language),
            reply_markup=build_request_address_inline_keyboard(addresses, page=0, language=language),
        )


async def _resident_cancel(message: Message, state: FSMContext, language: str) -> None:
    from .create import cancel_request  # create импортирует этот модуль — цикл только на уровне функций

    await cancel_request(message, state, lang=language)


RESIDENT_FLOW = ElevatorFlow(
    required_role="applicant",
    pick_state=RequestStates.elevator_pick,
    operational_state=RequestStates.elevator_operational,
    description_state=RequestStates.description,
    category_state=RequestStates.category,
    forbidden_key="requests.applicant_only",
    category_keyboard=lambda language: get_categories_inline_keyboard_with_cancel(language=language),
    on_no_building=_resident_no_building,
    cancel=_resident_cancel,
)


@router.callback_query(F.data.startswith(PICK_PREFIX), RequestStates.elevator_pick)
async def handle_elevator_pick(
    callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None
) -> None:
    lang = await _get_user_language(callback=callback)
    if await _deny_if_pending_callback(callback, user_status, language=lang):
        return
    await pick_elevator_step(callback, state, lang, RESIDENT_FLOW)


@router.callback_query(F.data.startswith(OPERATIONAL_PREFIX), RequestStates.elevator_operational)
async def handle_elevator_operational(
    callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None
) -> None:
    lang = await _get_user_language(callback=callback)
    if await _deny_if_pending_callback(callback, user_status, language=lang):
        return
    await operational_step(callback, state, lang, RESIDENT_FLOW)


@router.message(RequestStates.elevator_pick)
@router.message(RequestStates.elevator_operational)
async def process_elevator_step_text(message: Message, state: FSMContext) -> None:
    lang = await _get_user_language(message=message)
    await elevator_step_text(message, state, lang, RESIDENT_FLOW)
