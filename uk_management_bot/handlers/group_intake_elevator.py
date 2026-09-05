"""Групповой приём: фаза «лифт» для категории ``elevator`` (Ф4b, T9).

Вклинивается в callback-фазу ``handlers/group_intake.py`` ПОСЛЕ «Да» автора
(и ре-гейта): вместо немедленного ``save_request`` кандидат переводится в одну
из фаз и ОСТАЁТСЯ под тем же Redis-ключом ``(chat_id, message_id промпта)`` —
тот же механизм, что у выбора адреса ``gint:addr:<n>`` (pending.store_candidate
под ключом нажатого сообщения); промпт редактируется на месте.

Фазы (``candidate["phase"]``):
  * ``elevator_building`` — адрес автора на уровне двора: «уточните дом»,
    кнопки ``gint:bld:<n>`` (индекс в серверном ``building_options``; житель —
    дома двора с его approved-квартирами, staff — дома двора из справочника);
  * ``elevator_pick`` — ``gint:elv:{elevator_id}``: введённые лифты дома; id
    проверяется сервером (``ensure_elevator_usable_sync(building_id=…)`` по
    ``elevator_building_id`` из кандидата, не из callback);
  * ``elevator_operational`` — ``gint:op:1|0``: «лифт сейчас работает?»; ответ →
    GETDEL + ре-гейт + штатное создание с ``elevator_id``/``elevator_operational``.

Автоподстановка: ровно один введённый лифт в подъезде квартиры автора (или
единственный в доме) — сразу вопрос «работает?». Дом без лифтов — сообщение,
заявки нет. Отвечает ТОЛЬКО автор сообщения (проверка в group_intake_callback —
и в staff-группе, где «Да» может нажать коллега).

Таймаут (``ELEVATOR_ANSWER_TIMEOUT``): one-shot ``asyncio``-задача, поставленная
на «Да»; по истечении, если кандидат всё ещё в фазе лифта — GETDEL и правка
промпта «заявка не оформлена». Страховка на рестарт процесса — Redis-TTL фазы
(``ELEVATOR_PHASE_TTL``, чуть длиннее таймера): ответ после срока получает
«устарело», заявки нет. Двухшаговый расчёт (дом, подъезд → лифты) переиспользует
``_load_elevator_step`` личного бота (T7): ``selected_address`` приводится к
форме FSM-``data``. Флаг выключен / категория не «лифт» — модуль не участвует.
"""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.monitored_group import GROUP_KIND_STAFF
from uk_management_bot.database.session import run_db
from uk_management_bot.handlers.requests.create_elevator import (
    WORKS_STATUSES,
    ElevatorOption,
    _load_elevator_step,
    _option,
)
from uk_management_bot.keyboards.elevators import (
    build_group_elevator_operational_keyboard,
    build_group_elevator_pick_keyboard,
)
from uk_management_bot.services.elevator_service import (
    ELEVATOR_CATEGORY,
    ElevatorValidationError,
    ensure_elevator_usable_sync,
    status_label,
)
from uk_management_bot.services.group_intake import pending
from uk_management_bot.services.request_address import format_building_address
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

PHASE_BUILDING = "elevator_building"
PHASE_PICK = "elevator_pick"
PHASE_OPERATIONAL = "elevator_operational"
ELEVATOR_PHASES = frozenset({PHASE_BUILDING, PHASE_PICK, PHASE_OPERATIONAL})

# Ждём ответа автора (дом → лифт → «работает?») с момента «Да».
ELEVATOR_ANSWER_TIMEOUT = 30 * 60
# Redis-TTL кандидата в фазе лифта: длиннее таймера, чтобы проснувшийся таймер
# ещё застал кандидата и отредактировал промпт; при потере таймера истекает сам.
ELEVATOR_PHASE_TTL = ELEVATOR_ANSWER_TIMEOUT + 60
# Домов двора в выборе (staff — справочник целиком может быть большим).
_MAX_BUILDING_OPTIONS = 8
_BTN_LABEL_LIMIT = 60
# action-части callback_data (после ``gint:``).
_ACTION_BUILDING = "bld:"
_ACTION_ELEVATOR = "elv:"
_ACTION_OPERATIONAL = "op:"
_TEXT = "group_intake.elevator."


@dataclass(frozen=True)
class GroupElevatorStep:
    """Что показать после «Да»: ``building`` (уточнить дом) | ``none`` (лифтов
    нет) | ``auto`` (лифт выбран) | ``ok`` (выбор лифта). ``address`` — адрес
    после (авто)уточнения дома, им заменяется ``selected_address``."""

    verdict: str
    address: dict
    building_id: Optional[int] = None
    options: tuple[ElevatorOption, ...] = ()
    auto: Optional[ElevatorOption] = None
    dispatch_phone: str = ""
    building_options: tuple[dict, ...] = ()


# ══════════════════════════════════════════════════════════════════════════
# Предикаты (без БД)
# ══════════════════════════════════════════════════════════════════════════


def is_group_elevator_flow(candidate: dict) -> bool:
    """Фаза лифта — только для категории «лифт» при включённом флаге."""
    return bool(settings.ELEVATORS_ENABLED) and candidate.get("category") == ELEVATOR_CATEGORY


def is_elevator_action(action: str) -> bool:
    return action.startswith((_ACTION_BUILDING, _ACTION_ELEVATOR, _ACTION_OPERATIONAL))


def parse_operational(candidate: dict, action: str) -> Optional[bool]:
    """``op:1|0`` в фазе «работает?» → bool; иначе None (crafted / не та фаза)."""
    if candidate.get("phase") != PHASE_OPERATIONAL:
        return None
    value = action[len(_ACTION_OPERATIONAL):]
    if value not in ("0", "1"):
        return None
    return value == "1"


def _parse_int(raw: str) -> Optional[int]:
    return int(raw) if raw.isdigit() else None


def _bot_link() -> str:
    return f"https://t.me/{settings.BOT_USERNAME}"


# ══════════════════════════════════════════════════════════════════════════
# Sync-юниты (run_db)
# ══════════════════════════════════════════════════════════════════════════


def _building_option(address_id: int, address_type: str, building: Building) -> dict:
    label = format_building_address(building)
    return {"type": address_type, "id": address_id, "label_public": label, "label_full": label}


def _resident_building_options(db: Session, user_db_id: int, yard_id: int) -> list[dict]:
    """Дома двора, где у автора есть approved-квартира; по дому — одна квартира
    (primary → свежая), адрес заявки станет квартирным (подъезд известен)."""
    rows = db.execute(
        select(Apartment, UserApartment)
        .join(UserApartment, UserApartment.apartment_id == Apartment.id)
        .join(Apartment.building)
        .join(Building.yard)
        .options(contains_eager(Apartment.building).contains_eager(Building.yard))
        .where(
            UserApartment.user_id == user_db_id,
            UserApartment.status == "approved",
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Building.yard_id == yard_id,
        )
        .order_by(
            UserApartment.is_primary.desc(), UserApartment.requested_at.desc(), UserApartment.id.desc()
        )
    ).all()
    by_building: dict[int, dict] = {}
    for apartment, _link in rows:
        if apartment.building_id not in by_building:
            by_building[apartment.building_id] = _building_option(
                apartment.id, "apartment", apartment.building
            )
    return sorted(by_building.values(), key=lambda option: option["label_public"])


def _staff_building_options(db: Session, yard_id: int) -> list[dict]:
    """Staff-репорт: дома двора из справочника (принадлежность не требуется)."""
    rows = db.execute(
        select(Building)
        .join(Building.yard)
        .options(contains_eager(Building.yard))
        .where(Building.yard_id == yard_id, Building.is_active.is_(True), Yard.is_active.is_(True))
        .order_by(Building.address)
        .limit(_MAX_BUILDING_OPTIONS)
    ).scalars().all()
    return [_building_option(building.id, "building", building) for building in rows]


def _step_data(address: dict) -> dict:
    """``selected_address`` → ``data`` в форме FSM для ``_load_elevator_step``."""
    if address["type"] == "apartment":
        return {"address_type": "apartment", "apartment_id": address["id"]}
    return {"address_type": address["type"], "address_id": address["id"]}


def load_group_elevator_step_sync(
    db: Session, candidate: dict, user_db_id: Optional[int]
) -> GroupElevatorStep:
    """Двор → дома на выбор (один — берётся сразу); дом/квартира → лифты."""
    address = candidate["selected_address"]
    if address["type"] == "yard":
        if candidate.get("kind") == GROUP_KIND_STAFF:
            options = _staff_building_options(db, address["id"])
        else:
            options = _resident_building_options(db, user_db_id or 0, address["id"])
        if len(options) != 1:
            return GroupElevatorStep("building", address, building_options=tuple(options))
        address = options[0]
    step = _load_elevator_step(db, _step_data(address))
    return GroupElevatorStep(
        step.verdict, address, step.building_id, step.options, step.auto, step.dispatch_phone
    )


def pick_group_elevator_sync(
    db: Session, building_id: Optional[int], elevator_id: int
) -> Optional[ElevatorOption]:
    """Лифт по id из callback — только введённый и ТОГО дома, что в кандидате."""
    if building_id is None:
        return None
    try:
        elevator = ensure_elevator_usable_sync(db, elevator_id, building_id=building_id)
    except ElevatorValidationError as exc:
        logger.info("group_intake.elevator: лифт %s отклонён для дома %s: %s",
                    elevator_id, building_id, exc)
        return None
    return _option(elevator)


# ══════════════════════════════════════════════════════════════════════════
# Async: показ шагов (кандидат — под тем же ключом)
# ══════════════════════════════════════════════════════════════════════════


def _phase_payload(candidate: dict, **changes) -> dict:
    """Новый payload кандидата без ``v`` (версию ставит store_candidate)."""
    base = {key: value for key, value in candidate.items() if key != "v"}
    return {**base, **changes}


def _clip(label: str) -> str:
    return label if len(label) <= _BTN_LABEL_LIMIT else label[: _BTN_LABEL_LIMIT - 1] + "…"


def _building_keyboard(options: Sequence[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_clip(option["label_public"]),
                              callback_data=f"gint:{_ACTION_BUILDING}{index}")]
        for index, option in enumerate(options)
    ])


def _none_text(step: GroupElevatorStep, lang: str) -> str:
    if step.verdict != "none":
        return get_text(_TEXT + "no_buildings", language=lang)
    if step.dispatch_phone:
        return get_text(_TEXT + "none_in_building_phone", language=lang,
                        phone=html.escape(step.dispatch_phone))
    return get_text(_TEXT + "none_in_building", language=lang)


async def _store_phase(callback: CallbackQuery, payload: dict, lang: str) -> bool:
    """Сохранить фазу под ключом промпта; сбой → «устарело» (fail-closed)."""
    stored = await pending.store_candidate(
        callback.message.chat.id, callback.message.message_id, payload, ttl=ELEVATOR_PHASE_TTL,
    )
    if not stored:
        await callback.message.edit_text(get_text("group_intake.expired", language=lang))
    return stored


async def _show_operational(
    callback: CallbackQuery, base: dict, option: ElevatorOption, lang: str
) -> bool:
    """Зафиксировать лифт в кандидате и спросить «работает?» (+ подсказка о работах)."""
    payload = _phase_payload(
        base, phase=PHASE_OPERATIONAL, building_options=None,
        elevator_id=option.id, elevator_entrance=option.entrance, elevator_number=option.number,
    )
    if not await _store_phase(callback, payload, lang):
        return False
    text = get_text(_TEXT + "operational_prompt", language=lang,
                    entrance=option.entrance, elevator=option.number)
    if option.status in WORKS_STATUSES:
        hint = get_text(_TEXT + "works_hint", language=lang,
                        status=html.escape(status_label(option.status, lang)))
        text = f"{hint}\n{text}"
    await callback.message.edit_text(
        text, reply_markup=build_group_elevator_operational_keyboard(lang)
    )
    return True


async def _finish_without_request(callback: CallbackQuery, text: str) -> None:
    await pending.pop_candidate(callback.message.chat.id, callback.message.message_id)
    await callback.message.edit_text(text)


async def _apply_step(
    callback: CallbackQuery, candidate: dict, step: GroupElevatorStep, lang: str
) -> bool:
    """Показать шаг по вердикту; True — ждём ответа автора (кандидат в фазе)."""
    if step.verdict == "building":
        if not step.building_options:
            await _finish_without_request(callback, _none_text(step, lang))
            return False
        payload = _phase_payload(
            candidate, phase=PHASE_BUILDING, building_options=list(step.building_options)
        )
        if not await _store_phase(callback, payload, lang):
            return False
        await callback.message.edit_text(
            get_text(_TEXT + "need_building", language=lang),
            reply_markup=_building_keyboard(step.building_options),
        )
        return True
    if step.verdict not in ("auto", "ok"):
        await _finish_without_request(callback, _none_text(step, lang))
        return False
    base = _phase_payload(
        candidate, selected_address=step.address, elevator_building_id=step.building_id,
        building_options=None,
    )
    if step.verdict == "auto":
        return await _show_operational(callback, base, step.auto, lang)
    if not await _store_phase(callback, {**base, "phase": PHASE_PICK}, lang):
        return False
    await callback.message.edit_text(
        get_text(_TEXT + "pick_prompt", language=lang),
        reply_markup=build_group_elevator_pick_keyboard(step.options, lang),
    )
    return True


# ══════════════════════════════════════════════════════════════════════════
# Async: точки входа из group_intake_callback
# ══════════════════════════════════════════════════════════════════════════


async def start_elevator_phase(
    callback: CallbackQuery, bot: Bot, candidate: dict, user_db_id: int, lang: str,
    *, _db=None,
) -> None:
    """После «Да» и ре-гейта: вычислить шаг, показать, поставить таймер ожидания."""
    step = await run_db(
        lambda s: load_group_elevator_step_sync(s, candidate, user_db_id), db=_db
    )
    if await _apply_step(callback, candidate, step, lang):
        schedule_elevator_timeout(
            bot, callback.message.chat.id, callback.message.message_id, lang
        )


async def handle_building_pick(
    callback: CallbackQuery, candidate: dict, action: str, lang: str, *, _db=None
) -> None:
    """``gint:bld:<n>`` — индекс в серверном списке домов; id клиент не шлёт."""
    if candidate.get("phase") != PHASE_BUILDING:
        return
    options = candidate.get("building_options") or []
    index = _parse_int(action[len(_ACTION_BUILDING):])
    if index is None or not 0 <= index < len(options):
        return
    narrowed = {**candidate, "selected_address": options[index]}
    step = await run_db(lambda s: load_group_elevator_step_sync(s, narrowed, None), db=_db)
    await _apply_step(callback, candidate, step, lang)


async def handle_elevator_pick(
    callback: CallbackQuery, candidate: dict, action: str, lang: str, *, _db=None
) -> None:
    """``gint:elv:{id}`` — лифт проверяется сервером по дому из кандидата."""
    if candidate.get("phase") != PHASE_PICK:
        return
    elevator_id = _parse_int(action[len(_ACTION_ELEVATOR):])
    if elevator_id is None:
        return
    option = await run_db(
        lambda s: pick_group_elevator_sync(s, candidate.get("elevator_building_id"), elevator_id),
        db=_db,
    )
    if option is None:
        return
    await _show_operational(callback, candidate, option, lang)


# ══════════════════════════════════════════════════════════════════════════
# Таймаут ожидания ответа
# ══════════════════════════════════════════════════════════════════════════

_timeout_tasks: set[asyncio.Task] = set()


def schedule_elevator_timeout(bot: Bot, chat_id: int, message_id: int, lang: str) -> asyncio.Task:
    """One-shot задача: ссылка держится в реестре до завершения (иначе GC)."""
    task = asyncio.create_task(_expire_elevator_prompt(bot, chat_id, message_id, lang))
    _timeout_tasks.add(task)
    task.add_done_callback(_timeout_tasks.discard)
    return task


async def _expire_elevator_prompt(bot: Bot, chat_id: int, message_id: int, lang: str) -> None:
    """Нет ответа за таймаут → кандидат снят (GETDEL), промпт: «не оформлена»."""
    await asyncio.sleep(ELEVATOR_ANSWER_TIMEOUT)
    candidate = await pending.get_candidate(chat_id, message_id)
    if candidate is None or candidate.get("phase") not in ELEVATOR_PHASES:
        return
    if await pending.pop_candidate(chat_id, message_id) is None:
        return  # ответ успел прийти параллельно — заявку создаёт он
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=get_text(_TEXT + "timeout", language=lang, link=_bot_link()),
        )
    except TelegramAPIError as exc:
        logger.debug("group_intake.elevator: промпт таймаута не отредактирован: %s",
                     type(exc).__name__)
