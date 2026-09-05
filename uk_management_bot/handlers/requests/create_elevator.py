"""Создание заявки: шаги «лифт» между адресом и описанием (Ф4a-2, T7).

Для категории ``elevator`` при ``settings.ELEVATORS_ENABLED`` после выбора адреса
(дом известен только теперь) житель проходит два шага:

1. ``RequestStates.elevator_pick`` — введённые в эксплуатацию лифты дома
   (``elv:pick:{id}``). Квартира с заполненным подъездом и ровно одним лифтом в
   нём — автоподстановка без вопроса. Двор — «укажите дом», адресный шаг
   остаётся. Дом без лифтов — Р11 не обойти: сообщение с телефоном диспетчера
   (``board_config.dispatch_phone``, если задан) и возврат к выбору категории.
2. ``RequestStates.elevator_operational`` — «Лифт сейчас работает?»
   (``elv:op:1|0``); при статусе «в ремонте»/«на ТО» перед вопросом мягкая
   подсказка, не блокирующая заявку.

Ключи FSM: ``elevator_id``, ``elevator_operational`` (их читает
``save_request_sync``), ``elevator_entrance``/``elevator_number`` (сводка),
``elevator_building_id`` (дом адреса — сервер проверяет принадлежность лифта
ему при выборе; ``create_request_record`` перепроверит при сохранении).

DB-фаза — sync-юниты под ``run_db`` (гейт AUD3-37); за границу потока выходят
frozen-DTO. Авторизация ``elv:pick`` (ратчет authz): выбирать может только
applicant (``check_user_role_sync``), лифт — только своего дома
(``ensure_elevator_usable_sync(building_id=…)``). Флаг выключен — модуль
бездействует: ``is_elevator_flow`` False, штатный поток не меняется.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.elevators import (
    OPERATIONAL_PREFIX,
    PICK_PREFIX,
    build_elevator_operational_keyboard,
    build_elevator_pick_keyboard,
)
from uk_management_bot.keyboards.requests import (
    build_request_address_inline_keyboard,
    get_cancel_keyboard,
    get_categories_inline_keyboard_with_cancel,
)
from uk_management_bot.services.elevator_service import (
    ELEVATOR_CATEGORY,
    ElevatorValidationError,
    ensure_elevator_usable_sync,
    list_active_for_building_sync,
    status_label,
)
from uk_management_bot.services.request_handler_service import RequestHandlerService
from uk_management_bot.utils.auth_helpers import check_user_role_sync
from uk_management_bot.utils.business_time import to_business
from uk_management_bot.utils.helpers import get_text

from ._router import router
from .shared import (
    RequestStates,
    _deny_if_pending_callback,
    _get_user_language,
    _has_any_address,
    _load_user_request_addresses,
)

logger = logging.getLogger(__name__)

# Статусы, при которых перед вопросом «работает?» показывается мягкая подсказка.
WORKS_STATUSES: tuple[str, ...] = ("under_repair", "maintenance")
_SINCE_FORMAT = "%d.%m.%Y %H:%M"


# ══════════════════════════════════════════════════════════════════════════
# DTO — пересекают границу run_db (ORM за неё не выходит)
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ElevatorOption:
    id: int
    entrance: int
    number: int
    status: Optional[str]
    status_since: Optional[datetime]


@dataclass(frozen=True)
class ElevatorStep:
    verdict: str  # ok | auto | no_building | none
    building_id: Optional[int] = None
    options: tuple[ElevatorOption, ...] = ()
    auto: Optional[ElevatorOption] = None
    dispatch_phone: str = ""


def is_elevator_flow(data: dict) -> bool:
    """Шаги лифта включаются только для категории «лифт» при включённом флаге."""
    return bool(settings.ELEVATORS_ENABLED) and data.get("category") == ELEVATOR_CATEGORY


def save_failed_key(data: dict) -> str:
    """Текст отказа сохранения: для лифтового потока — свой (Р11 → None от save_request)."""
    return "requests.elevator.error_generic" if is_elevator_flow(data) else "errors.request_save_failed"


def elevator_summary_line(data: dict, language: str) -> str:
    """Строка «Лифт: подъезд N, лифт M · работает/не работает» для сводки; пусто без лифта."""
    if data.get("elevator_id") is None:
        return ""
    operational = data.get("elevator_operational")
    if operational is None:
        operational_text = get_text("common.not_specified", language=language)
    else:
        key = "operational_yes" if operational else "operational_no"
        operational_text = get_text(f"requests.elevator.{key}", language=language)
    return get_text(
        "requests.elevator.summary_line", language=language,
        entrance=data.get("elevator_entrance") or "?",
        elevator=data.get("elevator_number") or "?",
        operational=operational_text,
    )


# ══════════════════════════════════════════════════════════════════════════
# Sync-юниты (worker-поток через run_db)
# ══════════════════════════════════════════════════════════════════════════


def _option(elevator: Elevator) -> ElevatorOption:
    return ElevatorOption(
        id=elevator.id, entrance=elevator.entrance_number, number=elevator.elevator_number,
        status=elevator.current_status, status_since=elevator.status_since,
    )


def _request_building(
    service: RequestHandlerService, address_type: Optional[str],
    building_id: Optional[int], apartment_id: Optional[int],
) -> tuple[Optional[int], Optional[int]]:
    """(дом, подъезд квартиры) выбранного адреса; двор/legacy → (None, None)."""
    if address_type == "apartment" and apartment_id is not None:
        return service.get_apartment_location(apartment_id) or (None, None)
    if address_type == "building" and building_id is not None:
        return (building_id, None)
    return (None, None)


def _load_elevator_step(
    db: Session, address_type: Optional[str], building_id: Optional[int], apartment_id: Optional[int]
) -> ElevatorStep:
    """Что показать после адреса: список лифтов, автоподстановку или отказ."""
    service = RequestHandlerService(db)
    building_id, entrance = _request_building(service, address_type, building_id, apartment_id)
    if building_id is None:
        return ElevatorStep("no_building")
    options = tuple(
        _option(e) for e in list_active_for_building_sync(db, building_id) if e.is_commissioned
    )
    if not options:
        return ElevatorStep("none", building_id, dispatch_phone=service.get_dispatch_phone())
    in_entrance = [o for o in options if entrance is not None and o.entrance == entrance]
    if len(in_entrance) == 1:
        return ElevatorStep("auto", building_id, options, auto=in_entrance[0])
    return ElevatorStep("ok", building_id, options)


def _pick_elevator(
    db: Session, telegram_id: int, building_id: Optional[int], elevator_id: int
) -> tuple[str, Optional[ElevatorOption]]:
    """-> ('forbidden'|'invalid'|'ok', option). Только applicant; только лифт своего дома."""
    user = RequestHandlerService(db).get_user_by_telegram_id(telegram_id)
    if user is None or not check_user_role_sync(user.id, "applicant", db):
        return ("forbidden", None)
    if building_id is None:
        return ("invalid", None)
    try:
        elevator = ensure_elevator_usable_sync(db, elevator_id, building_id=building_id)
    except ElevatorValidationError as exc:
        logger.info("Лифт %s отклонён для дома %s: %s", elevator_id, building_id, exc)
        return ("invalid", None)
    return ("ok", _option(elevator))


# ══════════════════════════════════════════════════════════════════════════
# Async-шаги
# ══════════════════════════════════════════════════════════════════════════


def _works_hint(option: ElevatorOption, language: str) -> str:
    since = f"{to_business(option.status_since):{_SINCE_FORMAT}}" if option.status_since else "—"
    return get_text(
        "requests.elevator.works_hint", language=language,
        status=status_label(option.status, language), since=since,
    )


async def _edit_quietly(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.message.edit_text(text)
    except TelegramAPIError as exc:
        logger.debug("Сообщение шага лифта не отредактировано: %s", type(exc).__name__)


async def _ask_operational(
    message: Message, state: FSMContext, language: str, option: ElevatorOption
) -> None:
    """Зафиксировать лифт в FSM и спросить «работает?» (с подсказкой о работах)."""
    await state.update_data(
        elevator_id=option.id, elevator_entrance=option.entrance, elevator_number=option.number,
    )
    await state.set_state(RequestStates.elevator_operational)
    if option.status in WORKS_STATUSES:
        await message.answer(_works_hint(option, language))
    await message.answer(
        get_text("requests.elevator.operational_prompt", language=language),
        reply_markup=build_elevator_operational_keyboard(language),
    )


async def _ask_building(callback: CallbackQuery, language: str) -> None:
    """Двор не годится: попросить дом/квартиру и переотправить кнопки адресов."""
    await callback.message.answer(get_text("requests.elevator.need_building", language=language))
    addresses = await run_db(lambda s: _load_user_request_addresses(s, callback.from_user.id))
    if _has_any_address(addresses):
        await callback.message.answer(
            get_text("requests.choose_address_prompt", language=language),
            reply_markup=build_request_address_inline_keyboard(addresses, page=0, language=language),
        )


async def _back_to_category(
    callback: CallbackQuery, state: FSMContext, language: str, dispatch_phone: str
) -> None:
    """Дом без лифтов: Р11 обязателен — объяснить и вернуть к выбору категории."""
    if dispatch_phone:
        text = get_text("requests.elevator.none_in_building_phone", language=language,
                        phone=dispatch_phone)
    else:
        text = get_text("requests.elevator.none_in_building", language=language)
    await state.set_state(RequestStates.category)
    await callback.message.answer(
        text, reply_markup=get_categories_inline_keyboard_with_cancel(language=language),
    )


async def begin_elevator_step(
    callback: CallbackQuery, state: FSMContext, language: str, data: dict
) -> None:
    """Точка входа из handle_address_selection: адрес уже в ``data`` (state обновлён)."""
    step = await run_db(lambda s: _load_elevator_step(
        s, data.get("address_type"), data.get("building_id"), data.get("apartment_id"),
    ))
    if step.verdict == "no_building":
        await _ask_building(callback, language)
        return
    if step.verdict == "none":
        await _back_to_category(callback, state, language, step.dispatch_phone)
        return
    await state.update_data(elevator_building_id=step.building_id)
    if step.verdict == "auto":
        await _ask_operational(callback.message, state, language, step.auto)
        return
    await state.set_state(RequestStates.elevator_pick)
    await callback.message.answer(
        get_text("requests.elevator.pick_prompt", language=language),
        reply_markup=build_elevator_pick_keyboard(step.options, language),
    )


# ══════════════════════════════════════════════════════════════════════════
# Хендлеры
# ══════════════════════════════════════════════════════════════════════════


def _parse_int(raw: str) -> Optional[int]:
    return int(raw) if raw.isdigit() else None


@router.callback_query(F.data.startswith(PICK_PREFIX), RequestStates.elevator_pick)
async def handle_elevator_pick(
    callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None
) -> None:
    """Выбор лифта: id из callback проверяется сервером (applicant + лифт своего дома)."""
    lang = await _get_user_language(callback=callback)
    if await _deny_if_pending_callback(callback, user_status, language=lang):
        return
    elevator_id = _parse_int(callback.data[len(PICK_PREFIX):])
    if elevator_id is None:
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)
        return
    data = await state.get_data()
    verdict, option = await run_db(lambda s: _pick_elevator(
        s, callback.from_user.id, data.get("elevator_building_id"), elevator_id,
    ))
    if verdict == "forbidden":
        await callback.answer(get_text("requests.applicant_only", language=lang), show_alert=True)
        return
    if verdict != "ok" or option is None:
        await callback.answer(get_text("requests.elevator.invalid_choice", language=lang), show_alert=True)
        return
    await _edit_quietly(callback, get_text(
        "requests.elevator.picked", language=lang, entrance=option.entrance, elevator=option.number,
    ))
    await _ask_operational(callback.message, state, lang, option)
    await callback.answer()


@router.callback_query(F.data.startswith(OPERATIONAL_PREFIX), RequestStates.elevator_operational)
async def handle_elevator_operational(
    callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None
) -> None:
    """«Работает?» → elevator_operational в FSM → штатный шаг описания."""
    lang = await _get_user_language(callback=callback)
    if await _deny_if_pending_callback(callback, user_status, language=lang):
        return
    value = callback.data[len(OPERATIONAL_PREFIX):]
    if value not in ("0", "1"):
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)
        return
    operational = value == "1"
    await state.update_data(elevator_operational=operational)
    await state.set_state(RequestStates.description)
    key = "operational_yes" if operational else "operational_no"
    await _edit_quietly(callback, get_text(
        "requests.elevator.operational_saved", language=lang,
        operational=get_text(f"requests.elevator.{key}", language=lang),
    ))
    await callback.message.answer(
        get_text("requests.description", language=lang),
        reply_markup=get_cancel_keyboard(language=lang),
    )
    await callback.answer()


@router.message(RequestStates.elevator_pick)
@router.message(RequestStates.elevator_operational)
async def process_elevator_step_text(message: Message, state: FSMContext) -> None:
    """Текст вместо кнопки на шагах лифта: отмена — по кнопке, иначе подсказка."""
    lang = await _get_user_language(message=message)
    if message.text == get_text("buttons.cancel", language=lang):
        from .create import cancel_request

        await cancel_request(message, state, lang=lang)
        return
    await message.answer(get_text("requests.elevator.use_buttons", language=lang))
