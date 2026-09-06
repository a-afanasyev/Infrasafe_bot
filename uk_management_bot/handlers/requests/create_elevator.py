"""Создание заявки: шаги «лифт» между адресом/категорией и описанием (Ф4a-2, T7).

Для категории ``elevator`` при ``settings.ELEVATORS_ENABLED`` создающий заявку
проходит два шага, когда дом уже известен:

1. ``elevator_pick`` — введённые в эксплуатацию лифты дома (``elv:pick:{id}``).
   Ровно один пригодный лифт в доме, либо (у жителя) в подъезде его квартиры —
   автоподстановка без вопроса. Двор — «укажите дом». Дом без лифтов — Р11 не
   обойти: сообщение с телефоном диспетчера (``board_config.contacts.
   dispatch_phone``, если строка сохранена) и возврат к выбору категории.
2. ``elevator_operational`` — «Лифт сейчас работает?» (``elv:op:1|0``); при
   статусе «в ремонте»/«на ТО» самообслуживание (житель) сюда не доходит, если
   включён запрет Р18/Р18a (``flow.blocks_under_works`` × тумблер конфига
   ``allow_resident_requests_under_works``). Персоналу (обходчик) и при
   выключенном запрете остаётся прежняя мягкая подсказка.

Один код на два FSM. Житель (``create_elevator_resident.py``, адрес →
категория уже выбрана) и обходчик (``handlers/inspector_requests.py``,
категория после дома) различаются только состояниями, ролью, клавиатурой
категорий и отменой — это описывает ``ElevatorFlow``; шаги здесь
(``begin_elevator_step``, ``pick_elevator_step``, ``operational_step``,
``elevator_step_text``) общие, а хендлеры обоих роутеров — тонкие обёртки со
своим ``StateFilter`` в своих модулях. Здесь хендлеров нет.

Ключи FSM: ``elevator_id``, ``elevator_operational`` (их читает
``save_request_sync``), ``elevator_entrance``/``elevator_number`` (сводка),
``elevator_building_id`` (дом адреса — сервер проверяет принадлежность лифта
ему при выборе; ``create_request_record`` перепроверит при сохранении).
``clear_elevator_data`` снимает их при старте/повторном выборе категории —
иначе хвост брошенной лифтовой заявки уехал бы в заявку другой категории.

DB-фаза — sync-юниты под ``run_db`` (гейт AUD3-37), данные — через
``RequestHandlerService`` (гейт «без прямого ORM в хендлерах»); за границу
потока выходят frozen-DTO. Авторизация ``elv:pick``: роль потока
(``check_user_role_sync``) + approved + лифт своего дома
(``ensure_elevator_usable_sync(building_id=…)``). Флаг выключен — модуль
бездействует: ``is_elevator_flow`` False, штатный поток не меняется.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
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
from uk_management_bot.keyboards.requests import get_cancel_keyboard
from uk_management_bot.services.elevator_service import (
    ELEVATOR_CATEGORY,
    ElevatorValidationError,
    ensure_elevator_usable_sync,
    is_under_works,
    list_active_for_building_sync,
    status_label,
)
from uk_management_bot.services.request_handler_service import RequestHandlerService
from uk_management_bot.utils.auth_helpers import check_user_role_sync
from uk_management_bot.utils.business_time import to_business
from uk_management_bot.utils.helpers import get_text

from .elevator_works_block import (
    WorksBlock,
    works_block_sync,
    works_blocked_sync,
    works_blocked_text,
)

logger = logging.getLogger(__name__)

# Ключи FSM лифтового шага — снимаются при старте / повторном выборе категории.
ELEVATOR_DATA_KEYS: tuple[str, ...] = (
    "elevator_id", "elevator_operational", "elevator_entrance", "elevator_number",
    "elevator_building_id",
)
_SINCE_FORMAT = "%d.%m.%Y %H:%M"

# Публичный контракт шага лифта (его переиспользует групповой приём, Ф4b).
__all__ = [
    "ELEVATOR_DATA_KEYS", "ElevatorFlow", "ElevatorOption", "ElevatorStep", "PickedElevator",
    "begin_elevator_step", "clear_elevator_data", "elevator_save_failed_text",
    "elevator_step_text", "elevator_summary_line", "is_elevator_flow", "load_elevator_step",
    "operational_step", "parse_int", "pick_elevator_step", "save_failed_key", "to_option",
]


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
    # Р18a: автолифт под работами И запрет включён — подставлять его нельзя.
    works_blocked: bool = False


@dataclass(frozen=True)
class PickedElevator:
    """Результат ``elv:pick``: вердикт доступа + сам лифт + вердикт Р18a."""

    verdict: str  # ok | forbidden | invalid
    option: Optional[ElevatorOption] = None
    works_blocked: bool = False
    dispatch_phone: str = ""


@dataclass(frozen=True)
class ElevatorFlow:
    """Чем различаются FSM жителя и обходчика на лифтовом шаге."""

    required_role: str                 # роль для check_user_role_sync
    pick_state: State
    operational_state: State
    description_state: State
    category_state: State
    forbidden_key: str                 # текст отказа не-роли на elv:pick
    category_keyboard: Callable[[str], InlineKeyboardMarkup]
    on_no_building: Callable[[CallbackQuery, str], Awaitable[None]]
    cancel: Callable[[Message, FSMContext, str], Awaitable[None]]
    # Р18: самообслуживанию (житель) лифт «В ремонте»/«На ТО» запрещён;
    # обходчик — персонал, ему остаётся прежняя мягкая подсказка.
    blocks_under_works: bool = False


def is_elevator_flow(data: dict) -> bool:
    """Шаги лифта включаются только для категории «лифт» при включённом флаге."""
    return bool(settings.ELEVATORS_ENABLED) and data.get("category") == ELEVATOR_CATEGORY


def save_failed_key(data: dict) -> str:
    """Текст отказа сохранения: для лифтового потока — свой (Р11 → None от save_request)."""
    return "requests.elevator.error_generic" if is_elevator_flow(data) else "errors.request_save_failed"


async def clear_elevator_data(state: FSMContext) -> dict:
    """Снять ключи лифта из FSM (старт создания, повторный выбор категории); -> data."""
    data = await state.get_data()
    if not any(key in data for key in ELEVATOR_DATA_KEYS):
        return data
    cleaned = {key: value for key, value in data.items() if key not in ELEVATOR_DATA_KEYS}
    await state.set_data(cleaned)
    return cleaned


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


def to_option(elevator: Elevator) -> ElevatorOption:
    return ElevatorOption(
        id=elevator.id, entrance=elevator.entrance_number, number=elevator.elevator_number,
        status=elevator.current_status, status_since=elevator.status_since,
    )


def _request_building(
    service: RequestHandlerService, data: dict
) -> tuple[Optional[int], Optional[int]]:
    """(дом, подъезд квартиры) выбранного адреса; двор/legacy → (None, None).

    Житель кладёт ``building_id`` из резолвера (у квартиры — None, дом берём
    из квартиры); обходчик — только ``address_type="building"`` + ``address_id``.
    """
    address_type = data.get("address_type")
    if address_type == "apartment" and data.get("apartment_id") is not None:
        return service.get_apartment_location(int(data["apartment_id"])) or (None, None)
    if address_type == "building":
        building_id = data.get("building_id")
        if building_id is None:
            building_id = data.get("address_id")
        return (int(building_id), None) if building_id is not None else (None, None)
    return (None, None)


def load_elevator_step(
    db: Session, data: dict, *, blocks_under_works: bool = True
) -> ElevatorStep:
    """Что показать после адреса: список лифтов, автоподстановку или отказ.

    ``blocks_under_works`` — блокирует ли запрет Р18 этот канал (житель и
    групповой приём — да, обходчик — нет).
    """
    service = RequestHandlerService(db)
    building_id, entrance = _request_building(service, data)
    if building_id is None:
        return ElevatorStep("no_building")
    options = tuple(
        to_option(e) for e in list_active_for_building_sync(db, building_id) if e.is_commissioned
    )
    if not options:
        return ElevatorStep("none", building_id, dispatch_phone=service.get_dispatch_phone())
    # Автоподстановка: единственный лифт дома либо единственный в подъезде квартиры.
    candidates = [o for o in options if entrance is not None and o.entrance == entrance]
    if len(options) == 1:
        candidates = list(options)
    if len(candidates) == 1:
        # Конфиг и телефон читаются только когда автолифт под работами (Р18a).
        blocked, phone = (
            works_blocked_sync(db, candidates[0].status) if blocks_under_works else (False, "")
        )
        return ElevatorStep(
            "auto", building_id, options, auto=candidates[0],
            dispatch_phone=phone, works_blocked=blocked,
        )
    return ElevatorStep("ok", building_id, options)


def _pick_elevator(
    db: Session,
    telegram_id: int,
    role: str,
    building_id: Optional[int],
    elevator_id: int,
    *,
    blocks_under_works: bool,
) -> PickedElevator:
    """Approved-роль потока + лифт своего дома + вердикт Р18a для этого канала."""
    user = RequestHandlerService(db).get_user_by_telegram_id(telegram_id)
    if user is None or user.status != "approved" or not check_user_role_sync(user.id, role, db):
        return PickedElevator("forbidden")
    if building_id is None:
        return PickedElevator("invalid")
    try:
        elevator = ensure_elevator_usable_sync(db, elevator_id, building_id=building_id)
    except ElevatorValidationError as exc:
        logger.info("Лифт %s отклонён для дома %s: %s", elevator_id, building_id, exc)
        return PickedElevator("invalid")
    option = to_option(elevator)
    blocked, phone = works_blocked_sync(db, option.status) if blocks_under_works else (False, "")
    return PickedElevator("ok", option, works_blocked=blocked, dispatch_phone=phone)


# ══════════════════════════════════════════════════════════════════════════
# Общие async-шаги (параметризованы ElevatorFlow)
# ══════════════════════════════════════════════════════════════════════════


def _works_hint(option: ElevatorOption, language: str) -> str:
    since = f"{to_business(option.status_since):{_SINCE_FORMAT}}" if option.status_since else "—"
    return get_text(
        "requests.elevator.works_hint", language=language,
        status=status_label(option.status, language), since=since,
    )


def _blocked_text(option: ElevatorOption, dispatch_phone: str, language: str) -> str:
    return works_blocked_text(
        WorksBlock(
            entrance=option.entrance, number=option.number, status=option.status,
            status_since=option.status_since, dispatch_phone=dispatch_phone,
        ),
        language,
    )


async def _edit_quietly(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.message.edit_text(text)
    except TelegramAPIError as exc:
        logger.debug("Сообщение шага лифта не отредактировано: %s", type(exc).__name__)


async def _ask_operational(
    message: Message, state: FSMContext, language: str, option: ElevatorOption, flow: ElevatorFlow
) -> None:
    """Зафиксировать лифт в FSM и спросить «работает?» (с подсказкой о работах)."""
    await state.update_data(
        elevator_id=option.id, elevator_entrance=option.entrance, elevator_number=option.number,
    )
    await state.set_state(flow.operational_state)
    if is_under_works(option.status):
        # Сюда доходит только неблокирующий поток (персонал) — мягкая подсказка.
        await message.answer(_works_hint(option, language))
    await message.answer(
        get_text("requests.elevator.operational_prompt", language=language),
        reply_markup=build_elevator_operational_keyboard(language),
    )


async def _back_to_category(
    callback: CallbackQuery, state: FSMContext, language: str, dispatch_phone: str, flow: ElevatorFlow
) -> None:
    """Дом без лифтов: Р11 обязателен — объяснить и вернуть к выбору категории."""
    if dispatch_phone:
        text = get_text("requests.elevator.none_in_building_phone", language=language,
                        phone=html.escape(dispatch_phone))
    else:
        text = get_text("requests.elevator.none_in_building", language=language)
    await state.set_state(flow.category_state)
    await callback.message.answer(text, reply_markup=flow.category_keyboard(language))


async def begin_elevator_step(
    callback: CallbackQuery, state: FSMContext, language: str, data: dict, flow: ElevatorFlow
) -> None:
    """Точка входа после адреса+категории: ``data`` — актуальные данные FSM."""
    step = await run_db(
        lambda s: load_elevator_step(s, data, blocks_under_works=flow.blocks_under_works)
    )
    if step.verdict == "no_building":
        await flow.on_no_building(callback, language)
        return
    if step.verdict == "none":
        await _back_to_category(callback, state, language, step.dispatch_phone, flow)
        return
    await state.update_data(elevator_building_id=step.building_id)
    if step.verdict == "auto" and not step.works_blocked:
        await _ask_operational(callback.message, state, language, step.auto, flow)
        return
    if step.verdict == "auto":
        # Р18: автолифт под работами — не подставляем его молча, объясняем и
        # оставляем житель у клавиатуры лифтов дома (вдруг лифт не тот).
        await callback.message.answer(
            _blocked_text(step.auto, step.dispatch_phone, language)
        )
    await state.set_state(flow.pick_state)
    await callback.message.answer(
        get_text("requests.elevator.pick_prompt", language=language),
        reply_markup=build_elevator_pick_keyboard(step.options, language),
    )


def parse_int(raw: str) -> Optional[int]:
    return int(raw) if raw.isdigit() else None


async def pick_elevator_step(
    callback: CallbackQuery, state: FSMContext, language: str, flow: ElevatorFlow
) -> None:
    """``elv:pick:{id}``: id проверяется сервером (роль потока + лифт своего дома)."""
    elevator_id = parse_int(callback.data[len(PICK_PREFIX):])
    if elevator_id is None:
        await callback.answer(get_text("errors.default", language=language), show_alert=True)
        return
    data = await state.get_data()
    picked = await run_db(lambda s: _pick_elevator(
        s, callback.from_user.id, flow.required_role, data.get("elevator_building_id"), elevator_id,
        blocks_under_works=flow.blocks_under_works,
    ))
    verdict, option = picked.verdict, picked.option
    if verdict == "forbidden":
        await callback.answer(get_text(flow.forbidden_key, language=language), show_alert=True)
        return
    if verdict != "ok" or option is None:
        await callback.answer(
            get_text("requests.elevator.invalid_choice", language=language), show_alert=True,
        )
        return
    if picked.works_blocked:
        # Р18: лифт в FSM НЕ пишем, состояние остаётся ``pick_state``, клавиатура
        # лифтов дома на экране не тронута — житель может выбрать другой лифт.
        await callback.message.answer(_blocked_text(option, picked.dispatch_phone, language))
        await callback.answer()
        return
    await _edit_quietly(callback, get_text(
        "requests.elevator.picked", language=language,
        entrance=option.entrance, elevator=option.number,
    ))
    await _ask_operational(callback.message, state, language, option, flow)
    await callback.answer()


async def operational_step(
    callback: CallbackQuery, state: FSMContext, language: str, flow: ElevatorFlow
) -> None:
    """``elv:op:1|0`` → elevator_operational в FSM → штатный шаг описания."""
    value = callback.data[len(OPERATIONAL_PREFIX):]
    if value not in ("0", "1"):
        await callback.answer(get_text("errors.default", language=language), show_alert=True)
        return
    operational = value == "1"
    await state.update_data(elevator_operational=operational)
    await state.set_state(flow.description_state)
    key = "operational_yes" if operational else "operational_no"
    await _edit_quietly(callback, get_text(
        "requests.elevator.operational_saved", language=language,
        operational=get_text(f"requests.elevator.{key}", language=language),
    ))
    await callback.message.answer(
        get_text("requests.description", language=language),
        reply_markup=get_cancel_keyboard(language=language),
    )
    await callback.answer()


async def elevator_save_failed_text(data: dict, language: str, flow: ElevatorFlow) -> str:
    """Текст отказа сохранения заявки: гонка Р18 → блок-текст, иначе общий.

    Статус лифта мог смениться между выбором и «Подтвердить» — тогда
    ``create_request_record`` отказал именно из-за работ, и житель должен
    увидеть тот же текст, что на шаге выбора, а не «не удалось создать».
    Запрос делается только на пути отказа.
    """
    elevator_id = data.get("elevator_id")
    if not (flow.blocks_under_works and is_elevator_flow(data) and elevator_id is not None):
        return get_text(save_failed_key(data), language=language)
    block = await run_db(lambda s: works_block_sync(s, int(elevator_id)))
    if block is None:
        return get_text(save_failed_key(data), language=language)
    return works_blocked_text(block, language)


async def elevator_step_text(
    message: Message, state: FSMContext, language: str, flow: ElevatorFlow
) -> None:
    """Текст вместо кнопки на шагах лифта: отмена — по кнопке, иначе подсказка."""
    if message.text == get_text("buttons.cancel", language=language):
        await flow.cancel(message, state, language)
        return
    await message.answer(get_text("requests.elevator.use_buttons", language=language))
